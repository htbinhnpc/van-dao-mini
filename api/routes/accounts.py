from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.database import delete_rows, filter_value, insert_one, patch_rows, rest, select_one
from api.security import current_user
from api.services.game_client import GameAPIError, GameClient
from api.services.session_crypto import encrypt_session

router = APIRouter()

DEFAULT_CONFIG = {
    "enabled": False,
    "intervalMs": 60000,
    "autoMinor": True,
    "autoSalvage": False,
    "autoSalvageTier": 0,
    "autoSalvageMode": "salvage",
    "autoCleanup": False,
    "cleanupSkipConfirmation": False,
    "cleanupMode": "salvage",
    "cleanupMaxRarity": "pham",
    "cleanupMaxTier": 0,
    "cleanupKeepPerDefinition": 1,
    "cleanupMaxItems": 20,
    "cleanupSlots": [],
    "autoActivity": False,
    "activityType": "seclusion",
    "huntSpotId": "",
    "autoQuests": True,
    "autoDaily": True,
    "autoWeekly": False,
    "autoAchievements": False,
    "autoMail": True,
    "autoX2Daily": False,
    "autoEquipBest": False,
    "autoMinorTrial": False,
    "autoSectTasks": False,
    "autoSeasonTasks": False,
    "autoTitles": False,
    "autoPetAdopt": False,
    "autoNpcTalk": False,
    "autoNpcRewards": False,
    "autoHunt": False,
    "huntPetId": "",
    "huntReserveRuns": 0,
    "huntIntervalMin": 10,
    "autoFallbackHunt": True,
    "autoCraft": False,
    "craftRecipeId": "",
    "craftKeepQty": 10,
    "autoUse": False,
    "autoUseBuffs": True,
    "autoUseExp": False,
    "autoUseOnlyBest": True,
    "useThresholdMin": 15,
    "autoBoss": False,
    "bossIntervalMin": 10,
    "bossRegionId": "",
    "autoFarm": False,
    "farmHarvest": True,
    "farmPlant": True,
    "farmIncludeHabitats": True,
    "farmSeedMode": "best",
    "farmSeedId": "",
    "farmReserveStones": 0,
    "autoArena": False,
    "arenaMinPowerEdge": 5000,
    "arenaMaxRefresh": 3,
    "arenaMaxFights": 3,
}


class GameAccountLogin(BaseModel):
    username: str = Field(min_length=3, max_length=24)
    password: str = Field(min_length=8, max_length=128)
    label: str | None = Field(default=None, max_length=48)


def public_account(row: dict, config: dict | None = None) -> dict:
    return {
        "id": row["id"],
        "label": row["label"],
        "gameUsername": row.get("game_username"),
        "status": row.get("status", "active"),
        "enabled": row.get("enabled", False),
        "config": config or DEFAULT_CONFIG.copy(),
        "state": row.get("state_snapshot"),
        "lastTickAt": row.get("last_tick_at"),
        "lastError": row.get("last_error"),
        "createdAt": row.get("created_at"),
    }


async def owned_account(user_id: str, account_id: str) -> dict:
    account = await select_one(
        "game_accounts",
        f"id=eq.{filter_value(account_id)}&user_id=eq.{filter_value(user_id)}&select=*",
    )
    if not account:
        raise HTTPException(404, "Không tìm thấy tài khoản game.")
    return account


async def account_config(account_id: str) -> dict:
    row = await select_one(
        "account_configs", f"account_id=eq.{filter_value(account_id)}&select=config"
    )
    return {**DEFAULT_CONFIG, **(row or {}).get("config", {})}


@router.get("")
async def list_accounts(user: dict = Depends(current_user)) -> dict:
    rows = await rest(
        "game_accounts",
        query=f"user_id=eq.{filter_value(user['id'])}&select=id,label,game_username,status,enabled,state_snapshot,last_tick_at,last_error,created_at&order=created_at.asc",
    )
    result = []
    for row in rows or []:
        result.append(public_account(row, await account_config(row["id"])))
    return {"ok": True, "accounts": result}


@router.post("", status_code=201)
async def add_account(
    credentials: GameAccountLogin,
    user: dict = Depends(current_user),
) -> dict:
    username = credentials.username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,24}", username):
        raise HTTPException(422, "Tên tài khoản game không hợp lệ.")
    client = GameClient()
    try:
        cookie = await client.login(username, credentials.password)
        state = await GameClient(cookie=cookie).get_state()
    except GameAPIError as exc:
        raise HTTPException(exc.status_code if 400 <= exc.status_code < 500 else 502, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Không kết nối được máy chủ game.") from exc

    existing = await select_one(
        "game_accounts",
        f"user_id=eq.{filter_value(user['id'])}&game_username=eq.{filter_value(username)}&select=id",
    )
    encrypted = encrypt_session(cookie)
    label = (credentials.label or username).strip()[:48] or username
    if existing:
        rows = await patch_rows(
            "game_accounts",
            f"id=eq.{filter_value(existing['id'])}&user_id=eq.{filter_value(user['id'])}",
            {
                "label": label,
                "status": "active",
                "session_expires_at": None,
                "state_snapshot": state,
                "last_error": None,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                **encrypted,
            },
        )
        account = rows[0] if rows else await owned_account(user["id"], existing["id"])
        config = await account_config(account["id"])
    else:
        account = await insert_one(
            "game_accounts",
            {
                "user_id": user["id"],
                "label": label,
                "game_username": username,
                "status": "active",
                "state_snapshot": state,
                **encrypted,
            },
        )
        config = DEFAULT_CONFIG.copy()
        config.update(
            {
                "autoMinor": bool(state.get("character", {}).get("autoMinor")),
                "autoSalvageTier": int(state.get("settings", {}).get("autoSalvageTier") or 0),
                "autoSalvage": int(state.get("settings", {}).get("autoSalvageTier") or 0) > 0,
                "autoSalvageMode": state.get("settings", {}).get("autoSalvageMode") or "salvage",
                "activityType": state.get("activity", {}).get("type") or "seclusion",
                "huntSpotId": state.get("activity", {}).get("targetId") or "",
            }
        )
        await insert_one("account_configs", {"account_id": account["id"], "config": config})
    return {"ok": True, "account": public_account(account, config)}


@router.delete("/{account_id}")
async def remove_account(account_id: str, user: dict = Depends(current_user)) -> dict:
    await owned_account(user["id"], account_id)
    await delete_rows(
        "game_accounts",
        f"id=eq.{filter_value(account_id)}&user_id=eq.{filter_value(user['id'])}",
    )
    return {"ok": True}
