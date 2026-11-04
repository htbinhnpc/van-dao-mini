from __future__ import annotations

import hmac
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from api.database import filter_value, insert_one, patch_rows, select_one, rest
from api.security import create_session, current_user, hash_password, revoke_session, verify_password

router = APIRouter()


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=10, max_length=256)


class BootstrapCredentials(Credentials):
    setup_token: str = Field(min_length=16, max_length=256)


@router.post("/bootstrap", status_code=201)
async def bootstrap(data: BootstrapCredentials, response: Response) -> dict:
    """Create the first local user only; setup token is configured server-side."""
    expected = os.getenv("APP_SETUP_TOKEN", "")
    if not expected or not hmac.compare_digest(expected, data.setup_token):
        raise HTTPException(403, "Setup token không hợp lệ.")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,32}", data.username):
        raise HTTPException(422, "Username chỉ được gồm chữ, số, dấu chấm, gạch ngang hoặc gạch dưới.")
    existing = await rest("app_users", query="select=id&limit=1")
    if existing:
        raise HTTPException(409, "Dashboard đã được khởi tạo.")
    user = await insert_one(
        "app_users",
        {"username": data.username, "password_hash": hash_password(data.password)},
    )
    # If Supabase already had accounts from the older single-owner schema,
    # attach them to this first local user without touching their encrypted session.
    await patch_rows(
        "game_accounts",
        "user_id=is.null",
        {"user_id": user["id"]},
    )
    await create_session(user["id"], response)
    return {"ok": True, "user": {"id": user["id"], "username": user["username"]}}


@router.post("/login")
async def login(data: Credentials, response: Response) -> dict:
    user = await select_one(
        "app_users",
        f"username=eq.{filter_value(data.username)}&disabled_at=is.null&select=id,username,password_hash",
    )
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng.")
    await create_session(user["id"], response)
    return {"ok": True, "user": {"id": user["id"], "username": user["username"]}}


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    await revoke_session(request, response)
    return {"ok": True}


@router.get("/me")
async def me(user: dict = Depends(current_user)) -> dict:
    return {"authenticated": True, "user": user}
