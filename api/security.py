from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

from api.database import filter_value, insert_one, patch_rows, select_one

COOKIE_NAME = "vd_dashboard"
SESSION_DAYS = 7


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt${}${}${}${}${}".format(
        2**14,
        8,
        1,
        base64.urlsafe_b64encode(salt).decode(),
        base64.urlsafe_b64encode(derived).decode(),
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt64, digest64 = encoded.split("$", 5)
        if scheme != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt64)
        expected = base64.urlsafe_b64decode(digest64)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_session(user_id: str, response: Response) -> None:
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    await insert_one(
        "dashboard_sessions",
        {"user_id": user_id, "token_hash": _token_hash(token), "expires_at": expires.isoformat()},
    )
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 86400,
        httponly=True,
        secure=os.getenv("APP_ENV") == "production" or os.getenv("VERCEL") == "1",
        samesite="strict",
        path="/",
    )


async def current_user(request: Request) -> dict:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(401, "Cần đăng nhập dashboard.")
    digest = _token_hash(token)
    row = await select_one(
        "dashboard_sessions",
        f"token_hash=eq.{filter_value(digest)}&revoked_at=is.null&expires_at=gt.{filter_value(datetime.now(timezone.utc).isoformat())}&select=user_id",
    )
    if not row:
        raise HTTPException(401, "Phiên dashboard hết hạn hoặc đã bị thu hồi.")
    user = await select_one(
        "app_users", f"id=eq.{filter_value(row['user_id'])}&disabled_at=is.null&select=id,username"
    )
    if not user:
        raise HTTPException(401, "Tài khoản dashboard không khả dụng.")
    return user


async def revoke_session(request: Request, response: Response) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        await patch_rows(
            "dashboard_sessions",
            f"token_hash=eq.{filter_value(_token_hash(token))}&revoked_at=is.null",
            {"revoked_at": datetime.now(timezone.utc).isoformat()},
        )
    response.delete_cookie(
        COOKIE_NAME,
        path="/",
        httponly=True,
        secure=os.getenv("APP_ENV") == "production" or os.getenv("VERCEL") == "1",
        samesite="strict",
    )
