"""Small async PostgREST helper; the service-role key stays server-side."""

from __future__ import annotations

import os
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException


def _settings() -> tuple[str, str]:
    url = os.getenv("SUPABASE_URL", "").rstrip("/")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        raise HTTPException(503, "Supabase chưa được cấu hình.")
    return url, key


def filter_value(value: Any) -> str:
    return quote(str(value), safe="")


async def rest(
    table: str,
    *,
    method: str = "GET",
    query: str = "",
    body: Any = None,
    prefer: str | None = None,
) -> Any:
    url, key = _settings()
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    target = f"{url}/rest/v1/{table}" + (f"?{query}" if query else "")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(method, target, headers=headers, json=body)
    except httpx.HTTPError as exc:
        raise HTTPException(503, "Không kết nối được Supabase.") from exc
    if not response.is_success:
        # Do not return raw Postgres errors to the browser (they may reveal schema).
        raise HTTPException(502, f"Supabase request failed ({response.status_code}).")
    if not response.content:
        return None
    try:
        return response.json()
    except ValueError:
        return None


async def select_one(table: str, query: str) -> dict[str, Any] | None:
    rows = await rest(table, query=query)
    return rows[0] if rows else None


async def insert_one(table: str, body: dict[str, Any]) -> dict[str, Any]:
    rows = await rest(table, method="POST", query="select=*", body=body, prefer="return=representation")
    if not rows:
        raise HTTPException(502, "Supabase không trả bản ghi vừa tạo.")
    return rows[0]


async def patch_rows(table: str, query: str, body: dict[str, Any]) -> list[dict[str, Any]]:
    return await rest(table, method="PATCH", query=query, body=body, prefer="return=representation") or []


async def delete_rows(table: str, query: str) -> None:
    await rest(table, method="DELETE", query=query, prefer="return=minimal")
