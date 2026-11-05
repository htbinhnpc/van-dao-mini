"""Bounded, state-driven automation using only documented game commands."""

from __future__ import annotations

import asyncio
import json
import math
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from api.database import filter_value, insert_one, patch_rows
from api.routes.accounts import DEFAULT_CONFIG
from api.services.farming import rank_spots, update_losses
from api.services.arena import ARENA_MIN_LEVEL, last_fight_lost, my_power, pick_opponent, ranked_left
from api.services.game_client import GameClient
from api.services.game_rules import HUNT_TARGETS, NPC_REWARD_TIERS
from api.services.cleanup import config_rules, plan_cleanup
from api.services.session_crypto import decrypt_session

META_PATH = Path(__file__).resolve().parents[2] / "data" / "meta.json"
with META_PATH.open(encoding="utf-8") as meta_file:
    META = json.load(meta_file)


@dataclass
class TickBudget:
    deadline: float = field(default_factory=lambda: time.monotonic() + 40)
    attempts: int = 0
    stopped: bool = False
    error: str | None = None


_tick_budget: ContextVar[TickBudget | None] = ContextVar("tick_budget", default=None)


class IncompleteDisposal(ValueError):
    def __init__(self, state: dict):
        super().__init__("Game chưa xác nhận dọn đủ danh sách; đã giữ state mới và dừng vòng, không thử lại mù.")
        self.state = state


def _can_command() -> bool:
    budget = _tick_budget.get()
    return budget is None or (
        not budget.stopped and budget.attempts < 12 and time.monotonic() < budget.deadline
    )


def _ready(task: dict) -> bool:
    # Missing counters are not evidence that a task is ready (0 >= 0).
    return bool(task.get("id")) and task.get("claimed") is False and (
        task.get("current") is not None and task.get("target") is not None
        and _num(task["target"]) > 0 and _num(task["current"]) >= _num(task["target"])
    )


def _num(value: Any, default: float = 0) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (ValueError, TypeError, OverflowError):
        return default


async def log(account: dict, level: str, action: str, message: str = "", *, details: dict | None = None) -> None:
    await insert_one(
        "activity_logs",
        {
            "account_id": account["id"],
            "level": level,
            "action": action[:80],
            "message": (message or action)[:500],
            "details": details or {},
        },
    )


async def _command(client: GameClient, state: dict, command: str, payload: dict, account: dict, label: str, *, audit: dict | None = None) -> dict:
    if not _can_command():
        return state
    budget = _tick_budget.get()
    if budget:
        budget.attempts += 1
    details = None
    if command == "item.dispose":
        details = {**(audit or {}), "itemIds": payload["itemIds"], "mode": payload["mode"], "source": "autoCleanup",
                   "confirmation": "not_required", "requestedCount": len(payload["itemIds"]), "stateVersionBefore": state.get("stateVersion")}
        await log(account, "info", command, f"{label} (tự động, không hỏi xác nhận): bắt đầu, đang chờ kết quả game.", details={**details, "status": "started"})
    request = client.command(
        command,
        payload,
        expected_version=int(state.get("stateVersion") or 1),
    )
    result = await asyncio.wait_for(request, max(0.01, budget.deadline - time.monotonic())) if budget else await request
    next_state = result.get("state")
    if not isinstance(next_state, dict) or not next_state.get("stateVersion"):
        raise ValueError("Game command response thiếu state/stateVersion; dừng vòng để tránh dùng state cũ.")
    if command == "item.dispose":
        remaining = next_state.get("equipment")
        if (type(next_state.get("stateVersion")) is not int or next_state["stateVersion"] <= state.get("stateVersion", 0)
                or not isinstance(remaining, list)):
            raise ValueError("Game chưa xác nhận đã dọn đủ danh sách; dừng vòng, không thử lại mù.")
        if any(e.get("id") in payload["itemIds"] for e in remaining if isinstance(e, dict)):
            raise IncompleteDisposal(next_state)
    outcome = result.get("result") or {}
    lost = outcome.get("win") is False or outcome.get("won") is False or outcome.get("success") is False
    if command == "arena.fight":
        if outcome.get("won") is not None:
            delta = outcome.get("ratingDelta")
            label += f" · {'Thắng' if outcome['won'] else 'Không thắng'}" + (f" ({delta:+d} điểm)" if isinstance(delta, int) and not isinstance(delta, bool) else "")
        details = {**(audit or {}), "won": outcome.get("won"), "ratingDelta": outcome.get("ratingDelta"),
                   "rating": outcome.get("rating"), "tokens": outcome.get("tokens")}
    if command == "settle":
        label = f"Kết toán tu vi: +{(result.get('settle') or {}).get('expGained', 0)}"
    if command == "item.dispose" and details is not None:
        details = {**details, "status": "succeeded", "removedIds": payload["itemIds"], "remainingIds": [], "stateVersionAfter": next_state["stateVersion"]}
        label += " (tự động, không hỏi xác nhận) · Game đã xác nhận dọn đủ danh sách"
    await log(account, "warning" if lost else "success", command, f"{label} · chưa vượt qua" if lost else label, details=details)
    return next_state


async def _best_effort(client: GameClient, state: dict, command: str, payload: dict, account: dict, label: str, *, audit: dict | None = None) -> dict:
    try:
        return await _command(client, state, command, payload, account, label, audit=audit)
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        budget = _tick_budget.get()
        if budget:
            # A timeout may have committed on the server. Never send another
            # mutation using an uncertain version, or retry with a new key.
            budget.stopped = True
            budget.error = f"{command}: {message}"[:500]
        details = None
        if command == "item.dispose":
            details = {**(audit or {}), "itemIds": payload["itemIds"], "mode": payload["mode"], "source": "autoCleanup",
                       "confirmation": "not_required", "requestedCount": len(payload["itemIds"]),
                       "stateVersionBefore": state.get("stateVersion"), "status": "partial" if isinstance(exc, IncompleteDisposal) else "uncertain"}
            if isinstance(exc, IncompleteDisposal):
                remaining = {item.get("id") for item in exc.state["equipment"] if isinstance(item, dict) and isinstance(item.get("id"), str)}
                details.update(removedIds=[item_id for item_id in payload["itemIds"] if item_id not in remaining],
                               remainingIds=[item_id for item_id in payload["itemIds"] if item_id in remaining], stateVersionAfter=exc.state["stateVersion"])
        await log(account, "warning", command, f"{label}: {message[:350]}", details=details)
        return exc.state if isinstance(exc, IncompleteDisposal) else state


async def _claim_ready(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    periodic = state.get("periodic") or {}
    tasks: list[tuple[str, dict, str]] = []
    if config.get("autoQuests", True):
        tasks += [("quest.claim", {"questId": q["id"]}, "Nhận thưởng nhiệm vụ")
                  for q in (state.get("quests") or []) if q.get("status") == "claimable"]
    if config.get("autoDaily", True):
        remaining = max(0, 4 - int(_num(periodic.get("dailyClaims"))))
        tasks += [("daily.claim", {"taskId": t["id"]}, "Nhận mốc ngày")
                  for t in (periodic.get("daily") or [])
                   if _ready(t)][:remaining]
    if config.get("autoWeekly", False):
        tasks += [("weekly.claim", {"taskId": t["id"]}, "Nhận mốc tuần")
                  for t in (periodic.get("weekly") or [])
                   if _ready(t)][:3]
    if config.get("autoAchievements", False):
        tasks += [("achievement.claim", {"achievementId": t["id"]}, "Nhận thành tựu")
                  for t in (periodic.get("achievements") or [])
                   if _ready(t)][:6]
    for command, payload, label in tasks[:3]:
        state = await _best_effort(client, state, command, payload, account, label)
    x2 = state.get("x2") or {}
    if config.get("autoX2Daily", False) and x2 and not x2.get("dailyClaimed"):
        state = await _best_effort(client, state, "x2.daily.claim", {}, account, "Nhận thưởng mở rộng ngày")
    if config.get("autoMail", True) and _num(state.get("unreadMail", (state.get("mail") or {}).get("unreadCount"))) > 0:
        state = await _best_effort(client, state, "mail.claimAll", {}, account, "Nhận thư có quà")
    return state


async def _extra_rewards(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    tasks: list[tuple[str, dict, str]] = []
    if config.get("autoSectTasks") and (state.get("sect") or {}).get("id"):
        tasks += [("sect.task.claim", {"taskId": t["id"]}, "Nhận thưởng tông môn")
                  for t in ((state.get("sectExtra") or {}).get("tasks") or []) if _ready(t)]
    if config.get("autoSeasonTasks"):
        tasks += [("season.task.claim", {"taskId": t["id"]}, "Nhận thưởng lễ hội")
                  for t in ((state.get("season") or {}).get("tasks") or []) if _ready(t)]
    if config.get("autoTitles"):
        tasks += [("title.claim", {"titleId": t["id"]}, "Nhận danh hiệu (không tự mang)")
                  for t in ((state.get("ascend") or {}).get("titles") or [])
                  if t.get("id") and t.get("earned") is True and t.get("owned") is False]
    for command, payload, label in tasks[:3]:
        state = await _best_effort(client, state, command, payload, account, label)
    return state


async def _remember_attempt(account: dict, key: str, now: Any) -> None:
    data = {**(account.get("automation_data") or {}), key: now}
    await patch_rows("game_accounts", f"id=eq.{filter_value(account['id'])}", {"automation_data": data})
    account["automation_data"] = data


async def _equipment(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    if config.get("autoEquipBest") and any(e.get("location") == "bag" for e in (state.get("equipment") or [])):
        return await _best_effort(client, state, "equip.best", {}, account, "Tự trang bị theo bộ chọn của game")
    return state


async def _minor_trial(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    character = state.get("character") or {}
    gate = character.get("minorGate") or {}
    now = int(time.time() * 1000)
    last = _num((account.get("automation_data") or {}).get("minorTrialLastAttemptAt"))
    if (not config.get("autoMinorTrial") or character.get("next") != "minor"
            or gate.get("kind") != "trial" or gate.get("have") is None or gate.get("need") is None
            or _num(gate["have"]) >= _num(gate["need"]) or _num(gate["need"]) <= 0
            or character.get("exp") is None or character.get("expNeed") is None
            or _integer(character["expNeed"]) <= 0 or _integer(character["exp"]) < _integer(character["expNeed"])
            or now - last < 600_000 or not _can_command()):
        return state
    # Persist before attempting, so losing or a network failure cannot spam a trial.
    await _remember_attempt(account, "minorTrialLastAttemptAt", now)
    return await _best_effort(client, state, "minor.trial", {}, account, "Thử thách tiểu cảnh giới")


async def _npc(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    if config.get("autoNpcTalk"):
        ready = [n for n in (state.get("npcs") or [])
                 if n.get("id") and n.get("met") is True and n.get("talked") is False
                 and n.get("affinity") is not None and _num(n["affinity"]) < 1000]
        for npc in ready[:2]:
            state = await _best_effort(client, state, "npc.talk", {"npcId": npc["id"]}, account, "Trò chuyện đạo hữu (+thiện cảm ngày)")
    if config.get("autoNpcRewards"):
        ready = [(n["id"], tier) for n in (state.get("npcs") or [])
                 if n.get("id") and n.get("met") is True and isinstance(n.get("claimed"), list)
                 for tier, need in NPC_REWARD_TIERS
                 if tier not in n["claimed"] and _num(n.get("affinity")) >= need]
        for npc_id, tier_id in ready[:2]:
            state = await _best_effort(client, state, "npc.claim", {"npcId": npc_id, "tierId": tier_id}, account, "Nhận quà thiện cảm đạo hữu")
    return state


async def _pets(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    if config.get("autoPetAdopt"):
        pet = next((p for p in (state.get("pets") or [])
                    if p.get("id") and p.get("canAdopt") is True and p.get("owned") is False), None)
        if pet:
            state = await _best_effort(client, state, "pet.adopt", {"petId": pet["id"]}, account, "Thu nhận linh thú đã đủ điều kiện")
    if not config.get("autoHunt") or not _can_command():
        return state
    target = HUNT_TARGETS.get(config.get("huntPetId"))
    pet = next((p for p in (state.get("pets") or []) if target and p.get("id") == target["id"]), None)
    hunt = (state.get("x2") or {}).get("hunt") or {}
    now = int(time.time() * 1000)
    last = _num((account.get("automation_data") or {}).get("huntLastAttemptAt"))
    interval = max(1, _num(config.get("huntIntervalMin"), 10)) * 60_000
    if (not target or not pet or pet.get("owned") is not False or pet.get("canAdopt") is not False
            or _num((state.get("character") or {}).get("level")) < target["reqLevel"]
            or _num(hunt.get("runs")) <= max(0, _num(config.get("huntReserveRuns")))
            or not isinstance(hunt.get("seals"), dict)
            or _num(hunt["seals"].get(target["id"])) >= target["contractSeals"]
            or now - last < interval):
        return state
    await _remember_attempt(account, "huntLastAttemptAt", now)
    return await _best_effort(client, state, "hunt.run", {"petId": target["id"]}, account, f"Săn khế ấn {target['name']} (1 lượt)")


async def _settings(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    settings = state.get("settings") or {}
    salvage_tier = int(config.get("autoSalvageTier") or 1) if config.get("autoSalvage") and not config.get("autoCleanup") else 0
    desired = {
        "autoMinor": bool(config.get("autoMinor", True)),
        "autoSalvageTier": salvage_tier,
        "autoSalvageMode": "sell" if config.get("autoSalvageMode") == "sell" else "salvage",
    }
    actual = {
        "autoMinor": bool((state.get("character") or {}).get("autoMinor")),
        "autoSalvageTier": int(_num(settings.get("autoSalvageTier"))),
        "autoSalvageMode": settings.get("autoSalvageMode") or "salvage",
    }
    if desired == actual:
        return state
    return await _best_effort(client, state, "settings.set", desired, account, "Đồng bộ thiết lập game")


async def _cleanup(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    if not config.get("autoCleanup") or not _can_command():
        return state
    rules = config_rules(config)
    plan = plan_cleanup(state, rules, META)
    ids = [item["id"] for item in plan["items"]]
    audit = {"rules": rules.model_dump(), "scanned": plan["scanned"], "summary": plan["summary"],
             "items": [{key: item[key] for key in ("id", "name", "defId", "keptItemId")} for item in plan["items"]]}
    if not ids:
        await log(account, "info", "item.dispose", f"Dọn túi Mini (tự động): đã xét {plan['scanned']} món, không có bản trùng phù hợp; không gửi lệnh dọn.",
                  details={**audit, "source": "autoCleanup", "confirmation": "not_required", "mode": rules.mode, "status": "skipped", "itemIds": []})
        return state
    label = f"Dọn túi Mini: {'bán' if rules.mode == 'sell' else 'phân giải'} {len(ids)} bản trùng yếu hơn"
    return await _best_effort(client, state, "item.dispose", {"itemIds": ids, "mode": rules.mode}, account, label, audit=audit)


async def _activity(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    if not config.get("autoActivity"):
        return state
    activity_type = str(config.get("activityType") or "seclusion")
    payload: dict[str, Any] = {"type": activity_type}
    if activity_type == "farm":
        regions = {r.get("id") for r in (state.get("regions") or []) if r.get("unlocked")}
        level = _num((state.get("character") or {}).get("level"))
        power = my_power(state)
        now = int(time.time() * 1000)
        stored = (account.get("automation_data") or {}).get("farmSpotLosses") or {}
        losses = update_losses(stored, state.get("activity"), now_ms=now, power=power)
        if losses != stored:
            await _remember_attempt(account, "farmSpotLosses", losses)
        spots = {k: v for k, v in META.get("spots", {}).items()
                 if not config.get("huntSpotId") or v.get("id") == config["huntSpotId"]}
        # Best experience first (not "recommended level"): the highest-yield spot we may enter,
        # stepping down only past spots the game says we lose at, until a cool-down/power gain.
        ranked = rank_spots(spots, regions, level, losses=losses, now_ms=now, power=power,
                            avoid_losses=bool(config.get("autoFallbackHunt")))
        if ranked:
            payload["targetId"] = ranked[0]["id"]
        elif rank_spots(spots, regions, level, avoid_losses=False):
            payload = {"type": "seclusion"}  # every enterable spot was lost recently
        else:
            return state
    current = state.get("activity") or {}
    if current.get("type") == payload["type"] and (activity_type != "farm" or current.get("targetId") == payload.get("targetId")):
        return state
    return await _best_effort(client, state, "activity.set", payload, account, "Áp dụng hoạt động")


async def _craft(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    crafting = state.get("crafting") or {}
    if not config.get("autoCraft") or not crafting:
        return state
    free = max(0, int(_num(crafting.get("slots"))) - len(crafting.get("jobs") or []))
    if free == 0:
        return state
    materials = state.get("materials") or {}
    recipes = META.get("recipes", {})
    items = META.get("items", {})
    level = _num((state.get("character") or {}).get("level"))
    stones = _num((state.get("wallet") or {}).get("spirit_stone"))
    candidates = []
    for recipe in recipes.values():
        output_item = items.get((recipe.get("output") or {}).get("itemId"), {})
        use = output_item.get("use") or {}
        if use.get("type") not in {"cultivation_buff", "cultivation_exp"}:
            continue
        if config.get("craftRecipeId") and recipe.get("id") != config["craftRecipeId"]:
            continue
        if level < _num(recipe.get("reqLevel")) or stones < _num(recipe.get("stones")):
            continue
        if any(_num(materials.get(i.get("itemId"))) < _num(i.get("qty")) for i in recipe.get("inputs", [])):
            continue
        limit = recipe.get("weekLimit")
        if limit is not None and _num((crafting.get("weekUsed") or {}).get(recipe["id"])) >= _num(limit):
            continue
        score = _num(use.get("ratePct"), _num(use.get("exp")))
        candidates.append((score, recipe))
    if not candidates:
        return state
    recipe = max(candidates, key=lambda item: item[0])[1]
    output_id = (recipe.get("output") or {}).get("itemId")
    existing = _num(materials.get(output_id)) + sum(
        _num(job.get("recipeId") == recipe["id"]) * _num((recipe.get("output") or {}).get("qty"), 1)
        for job in crafting.get("jobs", [])
    )
    keep = max(0, int(_num(config.get("craftKeepQty", 10))))
    input_limits = [int(_num(materials.get(i.get("itemId"))) // max(1, _num(i.get("qty"), 1))) for i in recipe.get("inputs", [])]
    by_inputs = min(input_limits) if input_limits else free
    cost = _num(recipe.get("stones"))
    by_stones = int(stones // cost) if cost else free
    week_limit = recipe.get("weekLimit")
    by_week = free if week_limit is None else max(
        0,
        int(_num(week_limit) - _num((crafting.get("weekUsed") or {}).get(recipe["id"]))),
    )
    count = max(0, min(free, 8, keep - int(existing) if keep else free, by_inputs, by_stones, by_week))
    if not count:
        return state
    return await _best_effort(client, state, "craft.start", {"recipeId": recipe["id"], "count": count}, account, f"Luyện {recipe.get('name', recipe['id'])} ×{count}")


async def _use_pill(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    if not config.get("autoUse"):
        return state
    materials = state.get("materials") or {}
    items = [item for item in META.get("items", {}).values()
             if _num(materials.get(item.get("id"))) > 0
             and ((config.get("autoUseBuffs", True) and (item.get("use") or {}).get("type") == "cultivation_buff")
                  or (config.get("autoUseExp", False) and (item.get("use") or {}).get("type") == "cultivation_exp"))]
    items.sort(key=lambda item: _num((item.get("use") or {}).get("ratePct"), _num((item.get("use") or {}).get("exp"))), reverse=True)
    if not items:
        return state
    item = items[0]
    use = item.get("use") or {}
    if use.get("type") == "cultivation_buff":
        buff = next((b for b in state.get("buffs", []) if b.get("id") == f"buff:{item['id']}"), {})
        left = max(0, _num(buff.get("expiresAt")) - _num(state.get("serverNow"), time.time() * 1000))
        if left > _num(config.get("useThresholdMin", 15)) * 60000:
            return state
        if max(0, _num(use.get("maxTotalMs"), 14400000) - left) < _num(use.get("durationMs")):
            return state
        if config.get("autoUseOnlyBest", True) and left > 0:
            return state
    return await _best_effort(client, state, "item.use", {"itemId": item["id"], "qty": 1}, account, f"Dùng {item.get('name', item['id'])}")


async def _boss(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    if not config.get("autoBoss"):
        return state
    now = int(time.time() * 1000)
    history = (account.get("automation_data") or {}).get("bossLastFightAt", {})
    entries = []
    for region in state.get("regions", []):
        if not region.get("unlocked") or not region.get("bossCleared"):
            continue
        if config.get("bossRegionId") and region.get("id") != config["bossRegionId"]:
            continue
        region_meta = META.get("regions", {}).get(region.get("id"), {})
        boss = META.get("bosses", {}).get(region_meta.get("bossId"))
        if not boss or _num((state.get("character") or {}).get("level")) < _num(boss.get("reqLevel")):
            continue
        if _num(region.get("bossCooldownUntil")) > now:
            continue
        interval = max(0, _num(config.get("bossIntervalMin", 10))) * 60000
        if interval and now - _num(history.get(boss["id"])) < interval:
            continue
        entries.append((boss, region))
    entries.sort(key=lambda pair: _num(pair[0].get("reqLevel")))
    if not entries:
        return state
    target = entries[0][0]
    result = await _best_effort(client, state, "boss.fight", {"bossId": target["id"]}, account, f"Đánh boss {target.get('name', target['id'])}")
    if result is not state:
        history[target["id"]] = now
        updated = {**(account.get("automation_data") or {}), "bossLastFightAt": history}
        await patch_rows("game_accounts", f"id=eq.{filter_value(account['id'])}", {"automation_data": updated})
    return result


async def _arena(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    """Ranked arena: fight only opponents we out-power by ``arenaMinPowerEdge``; refresh the list when none fit."""
    if not config.get("autoArena") or not _can_command():
        return state
    data = account.get("automation_data") or {}
    now = int(time.time() * 1000)
    if _num(data.get("arenaIdleUntil")) > now:
        return state
    if _num((state.get("character") or {}).get("level")) < ARENA_MIN_LEVEL:
        return state
    budget = _tick_budget.get()

    async def read(pick: int) -> dict:
        request = client.get_arena(pick)
        return await asyncio.wait_for(request, max(0.01, budget.deadline - time.monotonic())) if budget else await request

    async def idle(minutes: int, key: str = "arenaIdleUntil") -> None:
        await _remember_attempt(account, key, now + minutes * 60_000)

    edge = max(0, _num(config.get("arenaMinPowerEdge"), 5000))
    max_refresh = max(0, int(_num(config.get("arenaMaxRefresh"), 3)))
    fights = max(1, int(_num(config.get("arenaMaxFights"), 3)))
    avoid = {k: v for k, v in (data.get("arenaLostAt") or {}).items() if now - _num(v) < 3_600_000}
    try:
        for _ in range(fights):
            power = my_power(state)
            if power is None or not _can_command():
                if power is None:
                    await log(account, "warning", "arena.fight", "Đấu trường: chưa biết lực chiến của bạn (state.power); bỏ qua, không đánh mù.")
                    await idle(30)
                break
            pick = 0
            arena = await read(pick)
            if ranked_left(arena) <= 0:
                await idle(60)
                break
            target = pick_opponent(arena, power, min_edge=edge, avoid=avoid, now_ms=now)
            while target is None and pick < max_refresh:
                pick += 1  # "Làm mới đối thủ": the game redraws 5 of the 20 closest by rating
                arena = await read(pick)
                target = pick_opponent(arena, power, min_edge=edge, avoid=avoid, now_ms=now)
            if target is None:
                await log(account, "info", "arena.fight",
                          f"Đấu trường: không có đối thủ cùng nhóm yếu hơn bạn ≥ {int(edge):,} lực chiến sau {pick} lần làm mới; không đánh.",
                          details={"myPower": power, "minEdge": edge, "refreshes": pick})
                await idle(15)
                break
            audit = {"defenderId": target["characterId"], "defenderName": target.get("name"), "myPower": power,
                     "theirPower": _num(target.get("power")), "powerEdge": power - _num(target.get("power")),
                     "theirRating": target.get("rating"), "refreshes": pick, "ranked": True}
            before = state
            state = await _best_effort(client, state, "arena.fight", {"defenderId": target["characterId"], "ranked": True},
                                       account, f"Đấu trường (đấu hạng) vs {target.get('name') or target['characterId']} · lực chiến {int(_num(target.get('power'))):,} (bạn {int(power):,})",
                                       audit=audit)
            if state is before:  # failed/uncertain: _best_effort already stopped the tick
                break
            try:
                if last_fight_lost(await read(0), target["characterId"]):
                    avoid[target["characterId"]] = now
                    await _remember_attempt(account, "arenaLostAt", avoid)
            except Exception:
                pass
    except Exception as exc:
        # Reads are harmless, but stop this tick's arena work and surface the error.
        await log(account, "warning", "arena.fight", f"Đấu trường: không đọc được bảng đối thủ: {str(exc)[:300] or type(exc).__name__}")
    return state


async def _farm(client: GameClient, state: dict, config: dict, account: dict) -> dict:
    cave = state.get("cave") or {}
    if not config.get("autoFarm") or not cave.get("unlocked"):
        return state
    fields = cave.get("fields") or []
    if config.get("farmHarvest", True):
        for field in [f for f in fields if _num(f.get("finishAt")) <= time.time() * 1000][:4]:
            state = await _best_effort(client, state, "field.harvest", {"plot": field.get("plot")}, account, f"Thu hoạch ô {field.get('plot')}")
    if not config.get("farmPlant", True):
        return state
    targets = [{"plot": p, "habitatId": None} for p in range(1, int(_num(cave.get("plots"))) + 1)]
    if config.get("farmIncludeHabitats", True):
        for habitat in sorted(META.get("habitats", {}).values(), key=lambda h: _num(h.get("order"))):
            opened = min(int(_num(habitat.get("plotCount"), 4)), int(_num(((state.get("x2") or {}).get("habitats") or {}).get(habitat["id"], {}).get("plots"))))
            targets.extend({"plot": int(habitat["plotStart"]) + i, "habitatId": habitat["id"]} for i in range(opened))
    occupied = {int(_num(f.get("plot"))) for f in state.get("cave", {}).get("fields", [])}
    materials, wallet = state.get("materials") or {}, state.get("wallet") or {}
    level = _num((state.get("character") or {}).get("level"))
    for target in targets:
        if target["plot"] in occupied:
            continue
        candidates = []
        for seed in META.get("seeds", {}).values():
            same_place = (seed.get("habitat") == target["habitatId"] or seed.get("alsoHabitat") == target["habitatId"]) if target["habitatId"] else not seed.get("habitat")
            if not same_place or level < _num(seed.get("reqLevel")):
                continue
            if not target["habitatId"] and target["plot"] < _num(seed.get("reqField"), 1):
                continue
            if _num(wallet.get("spirit_stone")) - _num(config.get("farmReserveStones")) < _num(seed.get("stones")):
                continue
            candidates.append(seed)
        if not candidates:
            continue
        if config.get("farmSeedMode") == "fast":
            candidates.sort(key=lambda s: _num(s.get("durationMs")))
        else:
            candidates.sort(key=lambda s: _num((s.get("yield") or {}).get("qty")) / max(1, _num(s.get("durationMs"))), reverse=True)
        preferred = config.get("farmSeedId")
        if preferred:
            candidates.sort(key=lambda s: s.get("id") != preferred)
        return await _best_effort(client, state, "field.plant", {"plot": target["plot"], "seedId": candidates[0]["id"]}, account, f"Gieo {candidates[0].get('name', candidates[0]['id'])}")
    return state


async def run_account_tick(account: dict, *, manual: bool = False, time_budget: float = 40) -> dict:
    if not account.get("enabled") and not manual:
        return {"skipped": True, "state": account.get("state_snapshot")}
    token = _tick_budget.set(TickBudget(deadline=time.monotonic() + max(0, min(40, time_budget))))
    try:
        return await _run_account_tick(account)
    finally:
        _tick_budget.reset(token)


async def _run_account_tick(account: dict) -> dict:
    cookie = decrypt_session(account)
    client = GameClient(cookie=cookie)
    budget = _tick_budget.get()
    assert budget is not None
    state = await asyncio.wait_for(client.get_state(), max(0.01, budget.deadline - time.monotonic()))
    config_row = account.get("config") or {}
    config = {**DEFAULT_CONFIG, **config_row}
    # Disable native drop disposal before explicitly settling when Mini owns
    # cleanup. No migration enables the new destructive action automatically.
    if config.get("autoCleanup"):
        state = await _settings(client, state, config, account)
    state = await _best_effort(client, state, "settle", {}, account, "Kết toán tu vi")
    state = await _settings(client, state, config, account)
    state = await _claim_ready(client, state, config, account)
    state = await _extra_rewards(client, state, config, account)
    state = await _equipment(client, state, config, account)
    state = await _cleanup(client, state, config, account)
    state = await _minor_trial(client, state, config, account)
    state = await _activity(client, state, config, account)
    state = await _pets(client, state, config, account)
    state = await _npc(client, state, config, account)
    state = await _use_pill(client, state, config, account)
    state = await _craft(client, state, config, account)
    state = await _boss(client, state, config, account)
    state = await _farm(client, state, config, account)
    state = await _arena(client, state, config, account)
    error = budget.error if budget else None
    await patch_rows(
        "game_accounts",
        f"id=eq.{filter_value(account['id'])}",
        {"state_snapshot": state, "last_tick_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "last_error": error},
    )
    return {
        "state": state, "completed": not error, "error": error,
        "commandsAttempted": budget.attempts if budget else 0,
        "deferred": not error and not _can_command(),
    }
