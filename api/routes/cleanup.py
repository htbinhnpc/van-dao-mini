"""Prepare equipment, then preview-bound, single-use inventory disposal."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.database import filter_value, insert_one, patch_rows, select_one
from api.routes.accounts import account_config, owned_account
from api.security import current_user
from api.services.automation import META
from api.services.cleanup import CleanupRules, plan_cleanup
from api.services.equipment import prepare_equipment, validate_equipment_response
from api.services.game_client import GameClient
from api.services.session_crypto import decrypt_session

router = APIRouter()


class PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: CleanupRules = Field(default_factory=CleanupRules)
    skipConfirmation: bool = Field(default=False, strict=True)
    prepareEquipment: bool = Field(default=False, strict=True)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    previewId: UUID
    itemIds: list[str] = Field(min_length=1, max_length=60)
    skipConfirmation: bool = Field(default=False, strict=True)

    @field_validator("itemIds")
    @classmethod
    def unique_ids(cls, values: list[str]) -> list[str]:
        if any(not value or len(value) > 160 for value in values) or len(set(values)) != len(values):
            raise ValueError("Danh sách món cần dọn không hợp lệ hoặc bị lặp.")
        return values


@router.post("/{account_id}/cleanup/preview")
async def preview_cleanup(account_id: str, request: PreviewRequest, user: dict = Depends(current_user)) -> dict:
    account = await owned_account(user["id"], account_id)
    if request.skipConfirmation and (await account_config(account_id)).get("cleanupSkipConfirmation") is not True:
        raise HTTPException(409, "Chưa bật tùy chọn dọn không hỏi xác nhận cho tài khoản này.")
    if not request.prepareEquipment:
        raise HTTPException(422, "Cần cho phép mặc đồ mạnh nhất và chuyển cường hóa trước khi xem trước dọn túi.")
    now = datetime.now(timezone.utc)
    lease = (now + timedelta(seconds=120)).isoformat()
    account_filter = f"id=eq.{filter_value(account_id)}&user_id=eq.{filter_value(user['id'])}"
    leased = await patch_rows("game_accounts", f"{account_filter}&or=(lease_until.is.null,lease_until.lt.{filter_value(now.isoformat())})", {"lease_until": lease})
    if not leased:
        raise HTTPException(409, "Tài khoản đang có lượt xử lý khác. Chờ xong rồi thử lại.")
    try:
        async with asyncio.timeout(40):
            client = GameClient(cookie=decrypt_session(account), timeout=15)
            state = await client.get_state()
            if type(state.get("stateVersion")) is not int or state["stateVersion"] < 1:
                raise ValueError("State game thiếu version.")

            async def send(current: dict, name: str, payload: dict, label: str) -> dict:
                await insert_one("activity_logs", {
                    "account_id": account_id, "level": "info", "action": name,
                    "message": f"{label}: bắt đầu chuẩn bị dọn túi.",
                    "details": {"status": "started", "source": "cleanup.prepare", **payload},
                })
                result = await client.command(name, payload, expected_version=current["stateVersion"])
                next_state = result.get("state")
                validate_equipment_response(current, next_state, name, payload)
                await patch_rows("game_accounts", account_filter, {"state_snapshot": next_state})
                await insert_one("activity_logs", {
                    "account_id": account_id, "level": "success", "action": name, "message": f"{label}: game đã xác nhận.",
                    "details": {"status": "succeeded", "source": "cleanup.prepare", **payload,
                                "stateVersionBefore": current["stateVersion"], "stateVersionAfter": next_state["stateVersion"]},
                })
                return next_state

            state = await prepare_equipment(state, META, send)
    except Exception as exc:
        try:
            await insert_one("activity_logs", {"account_id": account_id, "level": "warning", "action": "cleanup.prepare",
                             "message": "Chưa hoàn tất trang bị/chuyển cường hóa; không gửi lệnh dọn. Đồng bộ game trước khi thử lại.",
                             "details": {"status": "uncertain"}})
        except Exception:
            pass
        raise HTTPException(502, "Chưa hoàn tất mặc đồ/chuyển cường hóa (có thể thiếu phí). Chưa bán/phân giải; hãy đồng bộ game và kiểm tra nhật ký.") from exc
    finally:
        try:
            await patch_rows("game_accounts", f"{account_filter}&lease_until=eq.{filter_value(lease)}", {"lease_until": None})
        except Exception:
            pass  # Leave the expiring lease rather than masking a game outcome.
    plan = plan_cleanup(state, request.rules, META)
    expires = int(time.time()) + 120
    preview_id = None
    if plan["items"]:
        run = await insert_one("automation_runs", {
            "account_id": account_id, "status": "queued",
            "cursor": {"type": "cleanup_v2", "stateVersion": state["stateVersion"],
                       "rules": request.rules.model_dump(), "itemIds": [item["id"] for item in plan["items"]],
                       "expiresAt": expires},
        })
        preview_id = run["id"]
    elif request.skipConfirmation:
        await insert_one("activity_logs", {
            "account_id": account_id, "level": "info", "action": "cleanup.manual",
            "message": f"Dọn túi Mini (không hỏi xác nhận): đã xét {plan['scanned']} món, không có đồ dư phù hợp; không gửi lệnh dọn.",
            "details": {"source": "quick", "confirmation": "skipped", "status": "skipped", "mode": request.rules.mode,
                        "rules": request.rules.model_dump(), "itemIds": [], "scanned": plan["scanned"], "summary": plan["summary"]},
        })
    return {"ok": True, "plan": plan, "previewId": preview_id, "expiresAt": expires, "state": state}


@router.post("/{account_id}/cleanup/execute")
async def execute_cleanup(account_id: str, request: ExecuteRequest, user: dict = Depends(current_user)) -> dict:
    account = await owned_account(user["id"], account_id)
    run_id = str(request.previewId)
    run_filter = f"id=eq.{filter_value(run_id)}&account_id=eq.{filter_value(account_id)}"
    run = await select_one("automation_runs", f"{run_filter}&select=*")
    cursor = (run or {}).get("cursor") or {}
    if (not run or run.get("status") != "queued" or cursor.get("type") != "cleanup_v2"
            or type(cursor.get("expiresAt")) is not int or cursor["expiresAt"] <= time.time()):
        raise HTTPException(409, "Bản xem trước đã hết hạn hoặc đã dùng. Hãy xem trước lại; không gửi lại lệnh cũ.")
    approved = cursor.get("itemIds")
    if not isinstance(approved, list) or not set(request.itemIds).issubset(approved):
        raise HTTPException(422, "Chỉ được dọn các món trong bản xem trước đã xác nhận.")
    try:
        rules = CleanupRules.model_validate(cursor["rules"])
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, "Bản xem trước không hợp lệ; hãy tạo lại.") from exc
    if request.skipConfirmation and (await account_config(account_id)).get("cleanupSkipConfirmation") is not True:
        raise HTTPException(409, "Chưa bật tùy chọn dọn không hỏi xác nhận cho tài khoản này. Hãy bật và lưu trước khi dọn.")

    audit = {
        "itemIds": request.itemIds, "mode": rules.mode, "rules": rules.model_dump(),
        "source": "quick" if request.skipConfirmation else "manual",
        "confirmation": "skipped" if request.skipConfirmation else "dialog",
        "requestedCount": len(request.itemIds), "stateVersionBefore": cursor.get("stateVersion"),
    }
    label = "Bán" if rules.mode == "sell" else "Phân giải"
    context = "không hỏi xác nhận" if request.skipConfirmation else "có xác nhận"

    now = datetime.now(timezone.utc)
    lease = (now + timedelta(seconds=120)).isoformat()
    account_filter = f"id=eq.{filter_value(account_id)}&user_id=eq.{filter_value(user['id'])}"
    leased = await patch_rows("game_accounts", f"{account_filter}&or=(lease_until.is.null,lease_until.lt.{filter_value(now.isoformat())})", {"lease_until": lease})
    if not leased:
        raise HTTPException(409, "Tài khoản đang có lượt xử lý khác. Chờ xong rồi xem trước lại.")
    consumed = False
    command_attempted = False
    outcome_recorded = False
    try:
        async with asyncio.timeout(40):
            client = GameClient(cookie=decrypt_session(account), timeout=15)
            state = await client.get_state()
            if state.get("stateVersion") != cursor.get("stateVersion"):
                raise HTTPException(409, "State game đã thay đổi từ lúc xem trước. Hãy xem trước lại; chưa dọn món nào.")
            plan = plan_cleanup(state, rules, META)
            safe_ids = {item["id"] for item in plan["items"]}
            if not set(request.itemIds).issubset(safe_ids) or cursor["expiresAt"] <= time.time():
                raise HTTPException(409, "Danh sách không còn an toàn hoặc đã hết hạn. Hãy xem trước lại.")
            audit["items"] = [{key: item[key] for key in ("id", "name", "defId", "keptItemId")} for item in plan["items"] if item["id"] in request.itemIds]
            # Atomic consumption prevents double clicks, retries after a timeout,
            # or another instance from sending a second mutation for this preview.
            claimed = await patch_rows("automation_runs", f"{run_filter}&status=eq.queued", {
                "status": "running", "started_at": datetime.now(timezone.utc).isoformat(),
                "cursor": {**cursor, "selectedItemIds": request.itemIds, "skipConfirmation": request.skipConfirmation},
            })
            if not claimed:
                raise HTTPException(409, "Xác nhận này đã được xử lý. Không gửi lại lệnh cũ.")
            consumed = True
            # A destructive command is not sent unless its intent is recorded.
            await insert_one("activity_logs", {
                "account_id": account_id, "run_id": run_id, "level": "info", "action": "cleanup.manual",
                "message": f"Bắt đầu {label.lower()} {len(request.itemIds)} món ({context}); đang chờ game xác nhận kết quả.",
                "details": {**audit, "status": "started"},
            })
            command_attempted = True
            result = await client.command("item.dispose", {"itemIds": request.itemIds, "mode": rules.mode},
                                          expected_version=state["stateVersion"], idempotency_key=run_id)
        next_state = result.get("state")
        if (not isinstance(next_state, dict) or type(next_state.get("stateVersion")) is not int
                or next_state["stateVersion"] <= state["stateVersion"] or not isinstance(next_state.get("equipment"), list)):
            raise ValueError("Phản hồi game thiếu state xác nhận")
        await patch_rows("game_accounts", account_filter, {"state_snapshot": next_state})
        remaining = {item.get("id") for item in next_state["equipment"] if isinstance(item, dict) and isinstance(item.get("id"), str)}
        removed = [item_id for item_id in request.itemIds if item_id not in remaining]
        partial = len(removed) != len(request.itemIds)
        await insert_one("activity_logs", {
            "account_id": account_id, "run_id": run_id, "level": "warning" if partial else "success",
            "action": "cleanup.manual", "message": f"{label} {len(removed)}/{len(request.itemIds)} món ({context})." + (" Game chỉ xác nhận một phần; đã lưu state mới, không tự gửi lại." if partial else " Game đã xác nhận dọn đủ danh sách."),
            "details": {**audit, "status": "partial" if partial else "succeeded", "removedIds": removed,
                        "remainingIds": [item_id for item_id in request.itemIds if item_id in remaining],
                        "stateVersionAfter": next_state["stateVersion"]},
        })
        outcome_recorded = True
        await patch_rows("automation_runs", run_filter, {
            "status": "partial" if partial else "succeeded", "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        if partial:
            raise HTTPException(502, "Game chưa xác nhận dọn đủ danh sách. Đã lưu state mới; xem nhật ký, không thử lại mù.")
        return {"ok": True, "state": next_state, "removedCount": len(removed), "mode": rules.mode}
    except Exception as exc:
        if not outcome_recorded:
            try:
                if consumed:
                    await patch_rows("automation_runs", run_filter, {"status": "failed", "error_summary": "Không xác nhận được kết quả dọn; không tự retry.", "finished_at": datetime.now(timezone.utc).isoformat()})
                await insert_one("activity_logs", {
                    "account_id": account_id, "run_id": run_id, "level": "error" if command_attempted else "warning", "action": "cleanup.manual",
                    "message": f"Dọn túi Mini ({context}): " + ("Chưa xác nhận được kết quả; không tự retry. Đồng bộ game trước khi xem trước lại." if command_attempted else "Đã chặn trước khi gửi lệnh. " + (str(exc.detail) if isinstance(exc, HTTPException) else "Không đọc/kiểm tra/ghi nhật ký an toàn được.")),
                    "details": {**audit, "status": "uncertain" if command_attempted else "blocked"},
                })
            except Exception:
                pass
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(502, "Không xác nhận được kết quả dọn. Đồng bộ túi và kiểm tra nhật ký trước khi tạo bản xem trước mới; không tự gửi lại lệnh.") from exc
    finally:
        try:
            await patch_rows("game_accounts", f"{account_filter}&lease_until=eq.{filter_value(lease)}", {"lease_until": None})
        except Exception:
            pass  # Expiring lease remains; never clear another worker's lock.
