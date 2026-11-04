"""Encrypt game session cookies before writing them to Supabase."""

from __future__ import annotations

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _key() -> bytes:
    raw = os.environ.get("SESSION_ENCRYPTION_KEY", "")
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError("SESSION_ENCRYPTION_KEY must be 64 hex characters.") from exc
    if len(key) != 32:
        raise RuntimeError("SESSION_ENCRYPTION_KEY must decode to 32 bytes.")
    return key


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def encrypt_session(cookie: str) -> dict[str, str]:
    """Return independent ciphertext, IV, and GCM tag columns."""
    import secrets

    iv = secrets.token_bytes(12)
    sealed = AESGCM(_key()).encrypt(iv, cookie.encode("utf-8"), None)
    return {
        "session_ciphertext": _b64(sealed[:-16]),
        "session_iv": _b64(iv),
        "session_tag": _b64(sealed[-16:]),
    }


def decrypt_session(row: dict[str, str]) -> str:
    def decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))

    sealed = decode(row["session_ciphertext"]) + decode(row["session_tag"])
    return AESGCM(_key()).decrypt(decode(row["session_iv"]), sealed, None).decode("utf-8")
