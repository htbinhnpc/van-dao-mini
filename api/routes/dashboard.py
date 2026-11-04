from __future__ import annotations

import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from api.database import filter_value, insert_one, patch_rows, rest, select_one
from api.routes.accounts import DEFAULT_CONFIG, account_config, owned_account, public_account
from api.security import current_user
from api.services.automation import run_account_tick
from api.services.game_client import ALLOWED_COMMANDS, GameAPIError, GameClient
from api.services.session_crypto import decrypt_session

router = APIRouter()


class ConfigUpdate(BaseModel):
    config: dict[str, Any]


class CommandRequest(BaseModel):
    command: str
    payload: dict[str, Any] = Field(default_factory=dict)


def _config_for_update(current: dict, patch: dict) -> dict:
    unknown = set(patch) - set(DEFAULT_CONFIG)
    if unknown:
        raise HTTPException(422, f"Config không hỗ trợ: {', '.join(sorted(unknown))}")
    result = {**DEFAULT_CONFIG, **current, **patch}
    result["enabled"] = bool(result["enabled"])
    result["intervalMs"] = max(60_000, min(300_000, int(result.get("intervalMs") or 60_000)))
    result["bossIntervalMin"] = max(0, min(1440, int(result.get("bossIntervalMin") or 0)))
    result["useThresholdMin"] = max(0, min(240, int(result.get("useThresholdMin") or 0)))
    result["craftKeepQty"] = max(0, min(9999, int(result.get("craftKeepQty") or 0)))
    result["farmReserveStones"] = max(0, int(result.get("farmReserveStones") or 0))
    if result["activityType"] not in {"seclusion", "farm", "gather_herb", "mine_ore", "body_training"}:
        raise HTTPException(422, "Loại hoạt động không hợp lệ.")
    if result["autoSalvageMode"] not in {"salvage", "sell"}:
        raise HTTPException(422, "Chế độ dọn trang bị không hợp lệ.")
    if result["farmSeedMode"] not in {"best", "fast"}:
        raise HTTPException(422, "Chế độ chọn giống không hợp lệ.")
    # Keep expensive/consumable actions opt-in; clients must explicitly set true.
    for key in ("autoCraft", "autoUse", "autoUseExp", "autoBoss", "autoFarm"):
        result[key] = bool(result[key])
    return result


async def _account_state(account: dict) -> dict:
    try:
        state = await GameClient(cookie=decrypt_session(account)).get_state()
    except GameAPIError as exc:
        if exc.status_code in (401, 403):
            await patch_rows("game_accounts", f"id=eq.{filter_value(account['id'])}", {"status": "expired", "last_error": str(exc)[:500]})
        raise HTTPException(502, f"Không tải được trạng thái game: {exc}") from exc
    await patch_rows("game_accounts", f"id=eq.{filter_value(account['id'])}", {"state_snapshot": state, "status": "active", "last_error": None})
    return state


@router.get("/dashboard/overview")
async def overview(user: dict = Depends(current_user)) -> dict:
    rows = await rest(
        "game_accounts",
        query=f"user_id=eq.{filter_value(user['id'])}&select=id,label,game_username,status,enabled,state_snapshot,last_tick_at,last_error,created_at&order=created_at.asc",
    )
    accounts = []
    for row in rows or []:
        accounts.append(public_account(row, await account_config(row["id"])))
    return {"ok": True, "accounts": accounts, "selectedAccountId": accounts[0]["id"] if accounts else None}


@router.get("/meta")
async def game_metadata() -> dict:
    """Return the small, public subset of bundled game metadata used by the UI."""
    from api.services.automation import META

    return {
        "ok": True,
        "realms": META.get("realms", {}),
        "activities": META.get("activities", {}),
        "spots": META.get("spots", {}),
    }


@router.get("/game/server-status")
async def game_server_status() -> dict:
    """Public game maintenance indicator; never infer Active from a failed request."""
    checked_at = datetime.now(timezone.utc).isoformat()
    try:
        result = await GameClient().get_maintenance()
    except Exception:
        return {"status": "unknown", "checkedAt": checked_at}
    raw_maintenance = result.get("maintenance")
    maintenance = raw_maintenance if isinstance(raw_maintenance, dict) else None
    active = bool(maintenance and maintenance.get("active"))
    return {
        "status": "maintenance" if active else "active",
        "checkedAt": checked_at,
        "serverNow": result.get("serverNow"),
        "maintenance": maintenance if isinstance(maintenance, dict) else None,
    }


@router.get("/accounts/{account_id}/state")
async def get_state(account_id: str, refresh: bool = True, user: dict = Depends(current_user)) -> dict:
    account = await owned_account(user["id"], account_id)
    state = await _account_state(account) if refresh else account.get("state_snapshot")
    return {"ok": True, "state": state, "config": await account_config(account_id)}


@router.get("/accounts/{account_id}/items")
async def get_items(
    account_id: str,
    search: str = "",
    kind: str = "",
    user: dict = Depends(current_user),
) -> dict:
    account = await owned_account(user["id"], account_id)
    state = account.get("state_snapshot") or await _account_state(account)
    materials = state.get("materials") or {}
    from api.services.automation import META

    items = []
    query = search.strip().casefold()
    for item_id, quantity in materials.items():
        definition = META.get("items", {}).get(item_id, {"id": item_id, "name": item_id})
        if int(float(quantity or 0)) <= 0:
            continue
        if kind and definition.get("kind") != kind:
            continue
        if query and query not in str(definition.get("name", item_id)).casefold() and query not in item_id.casefold():
            continue
        items.append({**definition, "qty": quantity})
    items.sort(key=lambda item: (item.get("kind", ""), item.get("name", "")))
    return {
        "ok": True,
        "wallet": state.get("wallet", {}),
        "items": items,
        "capacity": state.get("inventory") or state.get("inventoryCapacity"),
    }


@router.get("/accounts/{account_id}/config")
async def get_config(account_id: str, user: dict = Depends(current_user)) -> dict:
    await owned_account(user["id"], account_id)
    return {"ok": True, "config": await account_config(account_id)}


@router.patch("/accounts/{account_id}/config")
async def save_config(account_id: str, update: ConfigUpdate, user: dict = Depends(current_user)) -> dict:
    account = await owned_account(user["id"], account_id)
    config = _config_for_update(await account_config(account_id), update.config)
    await patch_rows("account_configs", f"account_id=eq.{filter_value(account_id)}", {"config": config, "updated_at": datetime.now(timezone.utc).isoformat()})
    await patch_rows(
        "game_accounts",
        f"id=eq.{filter_value(account_id)}&user_id=eq.{filter_value(user['id'])}",
        {
            "enabled": config["enabled"],
            "next_run_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat() if config["enabled"] else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"ok": True, "config": config, "enabled": config["enabled"]}


@router.post("/accounts/{account_id}/config/sync")
async def sync_config(account_id: str, user: dict = Depends(current_user)) -> dict:
    account = await owned_account(user["id"], account_id)
    state = await _account_state(account)
    config = await account_config(account_id)
    config.update({
        "autoMinor": bool((state.get("character") or {}).get("autoMinor")),
        "autoSalvageTier": int(float((state.get("settings") or {}).get("autoSalvageTier") or 0)),
        "autoActivity": False,
        "activityType": (state.get("activity") or {}).get("type") or "seclusion",
        "huntSpotId": (state.get("activity") or {}).get("targetId") or "",
    })
    await patch_rows("account_configs", f"account_id=eq.{filter_value(account_id)}", {"config": config})
    return {"ok": True, "config": config}


@router.post("/accounts/{account_id}/command")
async def send_command(account_id: str, request: CommandRequest, user: dict = Depends(current_user)) -> dict:
    if request.command not in ALLOWED_COMMANDS:
        raise HTTPException(400, "Lệnh không nằm trong danh sách cho phép.")
    account = await owned_account(user["id"], account_id)
    state = await _account_state(account)
    try:
        result = await GameClient(cookie=decrypt_session(account)).command(
            request.command,
            request.payload,
            expected_version=int(state.get("stateVersion") or 1),
        )
    except GameAPIError as exc:
        raise HTTPException(502, f"Lệnh game thất bại: {exc}") from exc
    next_state = result.get("state") or state
    await patch_rows("game_accounts", f"id=eq.{filter_value(account_id)}", {"state_snapshot": next_state})
    await insert_one("activity_logs", {
        "account_id": account_id,
        "level": "success",
        "action": request.command,
        "message": f"Đã gửi lệnh {request.command}",
    })
    return {"ok": True, "result": result.get("result"), "state": next_state}


@router.post("/accounts/{account_id}/tick")
async def manual_tick(account_id: str, user: dict = Depends(current_user)) -> dict:
    account = await owned_account(user["id"], account_id)
    account["config"] = await account_config(account_id)
    result = await run_account_tick(account, manual=True)
    return {"ok": True, **result}


@router.get("/accounts/{account_id}/logs")
async def get_logs(account_id: str, limit: int = 80, user: dict = Depends(current_user)) -> dict:
    await owned_account(user["id"], account_id)
    limit = max(1, min(200, limit))
    rows = await rest(
        "activity_logs",
        query=f"account_id=eq.{filter_value(account_id)}&select=id,level,action,message,details,created_at&order=created_at.desc&limit={limit}",
    )
    return {"ok": True, "logs": rows or []}


@router.get("/dashboard/logs")
async def dashboard_logs(account_id: str, limit: int = 80, user: dict = Depends(current_user)) -> dict:
    return await get_logs(account_id, limit, user)


@router.api_route("/cron/automation", methods=["GET", "POST"])
async def automation_cron(request: Request, authorization: str | None = Header(default=None)) -> dict:
    secret = os.getenv("CRON_SECRET", "")
    supplied = (authorization or "").removeprefix("Bearer ")
    if not secret or not hmac.compare_digest(secret, supplied):
        raise HTTPException(401, "Cron secret không hợp lệ.")
    now = datetime.now(timezone.utc)
    rows = await rest(
        "game_accounts",
        query=f"enabled=eq.true&next_run_at=lte.{filter_value(now.isoformat())}&select=*&order=next_run_at.asc&limit=30",
    )
    started = time.monotonic()
    processed = []
    for candidate in rows or []:
        if time.monotonic() - started > 45:
            break
        lease_until = candidate.get("lease_until")
        lease_filter = f"lease_until=lt.{filter_value(now.isoformat())}" if lease_until else "lease_until=is.null"
        leased = await patch_rows(
            "game_accounts",
            f"id=eq.{filter_value(candidate['id'])}&enabled=eq.true&{lease_filter}",
            {"lease_until": (datetime.now(timezone.utc) + timedelta(seconds=55)).isoformat()},
        )
        if not leased:
            continue
        try:
            config = await account_config(candidate["id"])
            candidate["config"] = config
            result = await run_account_tick(candidate)
            next_run = datetime.now(timezone.utc) + timedelta(milliseconds=max(60_000, min(300_000, int(config.get("intervalMs") or 60_000))))
            await patch_rows("game_accounts", f"id=eq.{filter_value(candidate['id'])}", {
                "next_run_at": next_run.isoformat(), "lease_until": None,
                "last_tick_at": datetime.now(timezone.utc).isoformat(), "last_error": None,
            })
            processed.append({"accountId": candidate["id"], "ok": True, "skipped": result.get("skipped", False)})
        except Exception as exc:
            message = str(exc)[:500]
            await patch_rows("game_accounts", f"id=eq.{filter_value(candidate['id'])}", {
                "next_run_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(),
                "lease_until": None, "last_error": message,
            })
            try:
                await insert_one("activity_logs", {"account_id": candidate["id"], "level": "error", "action": "automation.tick", "message": message})
            except Exception:
                pass
            processed.append({"accountId": candidate["id"], "ok": False, "error": message})
    return {"ok": True, "scanned": len(rows or []), "processed": processed, "elapsedMs": int((time.monotonic() - started) * 1000)}
