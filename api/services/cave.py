"""Pure, resource-bounded cave-room upgrade planner. No network or mutations.

Definitions/costs mirror the public client bundle (2026-11-05). The game only
allows one room upgrade at a time and Mini never calls ``cave.rush``.
"""

from __future__ import annotations

import time
from collections import Counter

ROOMS = {
    "tu_linh": {
        "id": "tu_linh", "name": "Tụ Linh Trận", "maxLevel": 10,
        "baseStones": 300, "material": "item_frost_crystal", "baseQty": 4, "baseMinutes": 10,
        "effect": "+4% tốc độ tu vi mỗi cấp (cộng chung nhóm với đan dược).",
    },
    "tinh_that": {
        "id": "tinh_that", "name": "Tĩnh Thất", "maxLevel": 12,
        "baseStones": 250, "material": "item_iron_ore", "baseQty": 10, "baseMinutes": 8,
        "effect": "+1 giờ tích lũy khi vắng mặt mỗi cấp, từ 12 lên tối đa 24 giờ.",
    },
    "dan_phong": {
        "id": "dan_phong", "name": "Đan Phòng", "maxLevel": 6,
        "baseStones": 500, "material": "item_spirit_herb", "baseQty": 20, "baseMinutes": 15,
        "effect": "Cứ hai cấp thêm một lò chế tạo chạy song song.",
    },
    "khi_phong": {
        "id": "khi_phong", "name": "Khí Phòng", "maxLevel": 5,
        "baseStones": 500, "material": "item_iron_ore", "baseQty": 20, "baseMinutes": 15,
        "effect": "−6% thời gian chế tạo mỗi cấp.",
    },
    "linh_dien": {
        "id": "linh_dien", "name": "Linh Điền", "maxLevel": 4,
        "baseStones": 800, "material": "item_spirit_herb", "baseQty": 30, "baseMinutes": 20,
        "effect": "Mỗi cấp mở một ô trồng và một loại giống mới.",
    },
    "kho": {
        "id": "kho", "name": "Kho", "maxLevel": 8,
        "baseStones": 200, "material": "item_beast_hide", "baseQty": 10, "baseMinutes": 5,
        "effect": "+5 ô túi đồ mỗi cấp.",
    },
    "tang_bao": {
        "id": "tang_bao", "name": "Tàng Bảo Khố", "maxLevel": 5,
        "baseStones": 2000, "material": "item_iron_ore", "baseQty": 30, "baseMinutes": 30,
        "effect": "+10 ô trang bị cho Kho đồ dùng chung của tài khoản mỗi cấp (50 → 100).",
    },
}
ROOM_ORDER = ("tu_linh", "tinh_that", "dan_phong", "khi_phong", "linh_dien", "kho", "tang_bao")
CRAFT_ORDER = ("dan_phong", "khi_phong", "linh_dien", "kho", "tu_linh", "tang_bao", "tinh_that")
CULTIVATION_ORDER = ("tu_linh", "tinh_that", "dan_phong", "khi_phong", "linh_dien", "kho", "tang_bao")
ORDER_PRESETS = {"craft": CRAFT_ORDER, "cultivation": CULTIVATION_ORDER}
PRIORITY_REASONS = {"Nhiệm vụ đang làm", "Đan đột phá đại cảnh kế tiếp", "Bảo hiểm đột phá đại cảnh", "Bổ Khuyết Đan đột phá"}
MATERIAL_NAMES = {
    "item_frost_crystal": "Hàn Tinh", "item_iron_ore": "Thiết khoáng",
    "item_spirit_herb": "Linh thảo", "item_beast_hide": "Thú bì",
}


def integer(value, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return default
    try:
        return max(0, int(value))
    except (ValueError, OverflowError):
        return default


def upgrade_cost(room_id: str, level: int) -> dict | None:
    """Public-client formula for upgrading ``room_id`` from current ``level``."""
    room = ROOMS.get(room_id)
    if not room or type(level) is not int or not 0 <= level < room["maxLevel"]:
        return None
    return {
        "stones": round(room["baseStones"] * 1.7 ** level),
        "items": [{"itemId": room["material"], "qty": room["baseQty"] * (level + 1)}],
        "durationMs": room["baseMinutes"] * (level + 1) * 60_000,
    }


def parse_rooms(state: dict) -> dict[str, dict] | None:
    """Return the seven room records, or ``None`` when the snapshot is incomplete."""
    cave = state.get("cave")
    if not isinstance(cave, dict) or cave.get("unlocked") is not True:
        return None
    raw_rooms = cave.get("rooms")
    if not isinstance(raw_rooms, list):
        return None
    rooms: dict[str, dict] = {}
    for entry in raw_rooms:
        if not isinstance(entry, dict):
            return None
        room_id = entry.get("id")
        if room_id not in ROOMS or room_id in rooms:
            return None
        level = entry.get("level")
        if type(level) is not int or not 0 <= level <= ROOMS[room_id]["maxLevel"]:
            return None
        finish_at = entry.get("upgradeFinishAt")
        if finish_at is not None and (type(finish_at) is not int or finish_at <= 0):
            return None
        rooms[room_id] = {"id": room_id, "level": level, "upgradeFinishAt": finish_at}
    if set(rooms) != set(ROOMS):
        return None
    return rooms


def public_definitions() -> list[dict]:
    """Small metadata subset exposed by ``/api/v1/meta``; contains no account state."""
    return [
        {"id": room_id, "name": ROOMS[room_id]["name"], "maxLevel": ROOMS[room_id]["maxLevel"],
         "effect": ROOMS[room_id]["effect"]}
        for room_id in ROOM_ORDER
    ]


def public_rooms(rooms: dict[str, dict] | None) -> list[dict]:
    if rooms is None:
        return []
    return [
        {"id": room_id, "name": ROOMS[room_id]["name"], "maxLevel": ROOMS[room_id]["maxLevel"],
         "effect": ROOMS[room_id]["effect"], "level": rooms[room_id]["level"],
         "upgradeFinishAt": rooms[room_id]["upgradeFinishAt"]}
        for room_id in ROOM_ORDER
    ]


def _quest_rooms(state: dict, meta: dict, rooms: dict[str, dict]) -> list[str]:
    """Active cave_room objectives that still need work, in quest order."""
    required: list[str] = []
    seen: set[str] = set()
    quest_meta = meta.get("quests") or {}
    for quest in state.get("quests") or []:
        if not isinstance(quest, dict) or quest.get("status") != "active":
            continue
        objective = (quest_meta.get(quest.get("id")) or {}).get("objective") or {}
        if objective.get("type") != "cave_room":
            continue
        room_id, target = objective.get("roomId"), objective.get("level")
        if room_id not in ROOMS or type(target) is not int or target < 1:
            continue
        if room_id not in seen and rooms[room_id]["level"] < target:
            required.append(room_id)
            seen.add(room_id)
    return required


def _craft_reserves(state: dict, config: dict, meta: dict) -> tuple[int, Counter] | None:
    """Stones/materials craft still needs for quests and the next breakthrough."""
    try:
        from api.services.craft_profession import priorities
        entries = priorities(state, config, meta)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    stones, materials = 0, Counter()
    for entry in entries:
        if entry.get("reason") not in PRIORITY_REASONS:
            continue
        recipe = entry["recipe"]
        for item in recipe.get("inputs") or []:
            if not isinstance(item, dict) or not isinstance(item.get("itemId"), str):
                return None
            materials[item["itemId"]] += integer(item.get("qty")) * entry["count"]
        stones += integer(recipe.get("stones")) * entry["count"]
    return stones, materials


def _affordable(state: dict, cost: dict, reserve_stones: int, reserve_materials: Counter,
                floor: int) -> tuple[bool, str]:
    wallet = integer((state.get("wallet") or {}).get("spirit_stone"))
    if wallet - reserve_stones < cost["stones"]:
        return False, f"Giữ {reserve_stones} linh thạch dự trữ; cần {cost['stones']}."
    materials = state.get("materials") or {}
    for item in cost["items"]:
        item_id, qty = item["itemId"], item["qty"]
        have = integer(materials.get(item_id))
        needed = floor + reserve_materials[item_id] + qty
        if have < needed:
            return False, f"Thiếu {MATERIAL_NAMES.get(item_id, item_id)} dư trên sàn dự trữ (có {have}, cần {needed})."
    return True, ""


def plan_cave_upgrade(state: dict, config: dict, meta: dict, *, now_ms: int | None = None) -> dict:
    """Plan at most one ``cave.upgrade`` command; the worker re-plans after state changes."""
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    result = {"phase": "ready", "rooms": [], "action": None, "reason": "", "blocked": [], "active": None,
              "reserve": {"stones": 0, "materials": {}}}
    rooms = parse_rooms(state)
    result["rooms"] = public_rooms(rooms)
    if not config.get("autoCaveUpgrade"):
        result["phase"], result["reason"] = "disabled", "Tự nâng động phủ đang tắt; xem tiến độ không gửi lệnh game."
        return result
    if rooms is None:
        result["phase"] = "unknown"
        result["reason"] = "Chưa có cave.unlocked/rooms hợp lệ; không suy đoán phòng hay cấp."
        return result

    active = next((room for room in rooms.values() if room["upgradeFinishAt"] is not None), None)
    if active:
        result["active"] = {"id": active["id"], "name": ROOMS[active["id"]]["name"],
                            "level": active["level"], "upgradeFinishAt": active["upgradeFinishAt"]}
        result["reason"] = f"Đang nâng {ROOMS[active['id']]['name']}; mỗi lúc chỉ một phòng."
        return result

    reserve_stones = integer(config.get("caveReserveStones", 1000))
    floor = integer(config.get("caveMatFloor", 20))
    reserve_materials: Counter = Counter()
    if config.get("autoCraft") or config.get("autoMajorBreakthrough"):
        # Keep enough for craft quests and the next breakthrough; missing data
        # must never authorize spending that could starve those priorities.
        reserves = _craft_reserves(state, config, meta)
        if reserves is None:
            result["reason"] = "Chưa đủ dữ liệu chế tạo để giữ tài nguyên; tạm dừng nâng phòng."
            return result
        craft_stones, reserve_materials = reserves
        reserve_stones += craft_stones + integer(config.get("craftReserveStones", 1000))
        floor = max(floor, integer(config.get("craftMatFloor", 20)))
    if config.get("autoMajorBreakthrough"):
        from api.services.breakthrough import next_major
        major = next_major(state, at_cap=False)
        if major:
            for item in major["materials"]:
                reserve_materials[item["itemId"]] += item["qty"]
    result["reserve"] = {"stones": reserve_stones, "materials": dict(reserve_materials)}

    def action_for(room_id: str, reason: str) -> dict:
        room = rooms[room_id]
        cost = upgrade_cost(room_id, room["level"])
        assert cost is not None
        return {"roomId": room_id, "name": ROOMS[room_id]["name"], "level": room["level"],
                "targetLevel": room["level"] + 1, "stones": cost["stones"],
                "items": cost["items"], "durationMs": cost["durationMs"], "reason": reason}

    required = _quest_rooms(state, meta, rooms)
    if required:
        room_id = required[0]
        cost = upgrade_cost(room_id, rooms[room_id]["level"])
        assert cost is not None
        affordable, why = _affordable(state, cost, reserve_stones, reserve_materials, floor)
        if affordable:
            result["action"] = action_for(room_id, "Nhiệm vụ động phủ đang làm")
            result["reason"] = result["action"]["reason"]
            return result
        result["blocked"].append({"name": ROOMS[room_id]["name"], "reason": why})
        result["reason"] = "Phòng cho nhiệm vụ động phủ chưa đủ tài nguyên dư; chờ, không tiêu vào phòng khác."
        return result

    preset = config.get("caveRoomOrder", "craft")
    if preset == "balanced":
        candidates = sorted(
            (room_id for room_id in ROOM_ORDER if rooms[room_id]["level"] < ROOMS[room_id]["maxLevel"]),
            key=lambda room_id: (rooms[room_id]["level"] / ROOMS[room_id]["maxLevel"], ROOM_ORDER.index(room_id)),
        )
    else:
        candidates = [room_id for room_id in ORDER_PRESETS.get(preset, CRAFT_ORDER)
                      if rooms[room_id]["level"] < ROOMS[room_id]["maxLevel"]]
    if not candidates:
        result["reason"] = "Tất cả phòng đã đạt cấp tối đa."
        return result
    for room_id in candidates:
        cost = upgrade_cost(room_id, rooms[room_id]["level"])
        assert cost is not None
        affordable, why = _affordable(state, cost, reserve_stones, reserve_materials, floor)
        if affordable:
            label = {"craft": "ưu tiên chế tạo", "cultivation": "ưu tiên tu luyện"}.get(preset, "cân bằng cấp thấp")
            result["action"] = action_for(room_id, f"Thứ tự {label}")
            result["reason"] = result["action"]["reason"]
            return result
        result["blocked"].append({"name": ROOMS[room_id]["name"], "reason": why})
    result["reason"] = "Chưa có phòng nào đủ linh thạch/nguyên liệu dư trên mức dự trữ."
    return result


def validate_upgrade_response(before: dict, after: dict, room_id: str) -> None:
    """Reject an uncertain/inconsistent response; callers must not retry it."""
    if not isinstance(after, dict):
        raise ValueError("Phản hồi nâng phòng thiếu state.")
    before_version, after_version = before.get("stateVersion"), after.get("stateVersion")
    if type(after_version) is not int or type(before_version) is not int or after_version <= before_version:
        raise ValueError("Phản hồi nâng phòng không tăng stateVersion; dừng, không retry.")
    before_rooms, after_rooms = parse_rooms(before), parse_rooms(after)
    if before_rooms is None or after_rooms is None:
        raise ValueError("Phản hồi nâng phòng thiếu danh sách phòng hợp lệ; dừng.")
    if room_id not in ROOMS:
        raise ValueError("Phòng động phủ không hợp lệ.")
    old, new = before_rooms[room_id], after_rooms[room_id]
    if new["level"] not in (old["level"], old["level"] + 1):
        raise ValueError("Cấp phòng sau nâng không hợp lệ; dừng.")
    if new["upgradeFinishAt"] is None or new["upgradeFinishAt"] <= 0:
        raise ValueError("Game chưa đặt thời gian nâng phòng; dừng.")
    if any(after_rooms[other]["level"] != before_rooms[other]["level"] for other in ROOMS if other != room_id):
        raise ValueError("Phản hồi làm thay đổi phòng khác; dừng.")
    active = [other for other in ROOMS if after_rooms[other]["upgradeFinishAt"] is not None]
    if active != [room_id]:
        raise ValueError("Phản hồi không xác nhận đúng một phòng đang nâng; dừng.")
