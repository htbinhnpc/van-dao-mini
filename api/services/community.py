"""Pure sect donation and shared-boss policies, from public client 2026-11-06.

No purchases, guild stone donations, PvP or automatic reward-branch choices.
"""

from collections import Counter

from api.services.breakthrough import natural, next_major
from api.services.craft_profession import URGENT_REASONS, priorities

DONATION_VALUES = {
    "item_spirit_herb": 1, "item_iron_ore": 1, "item_beast_hide": 1,
    "item_frost_crystal": 4, "item_ember_sand": 8,
    "item_ancient_resin": 12, "item_moon_shard": 16,
}
PENDING_FLAGS = {"donate": "autoSectDonate", "checkin": "autoGuildCheckin",
                 "world": "autoWorldBoss", "guild": "autoGuildBoss"}


def membership_id(value) -> str | None:
    value = value.get("id") if isinstance(value, dict) else value
    return value if isinstance(value, str) and value else None


def plan_donation(state: dict, config: dict, meta: dict) -> dict:
    result = {"action": None, "reason": "Quyên góp tông môn đang tắt."}
    if not config.get("autoSectTasks") or not config.get("autoSectDonate"):
        return result
    result["reason"] = "Thiếu dữ liệu tông môn/kho hoặc giới hạn ngày; không đoán."
    sect, materials = state.get("sect"), state.get("materials")
    if not isinstance(sect, dict) or not membership_id(sect) or not isinstance(materials, dict):
        return result
    used, daily = natural(sect.get("donatedToday")), natural(config.get("sectDonateDaily", 400))
    floors = [natural(config.get("sectDonateMatFloor", 100)), natural(config.get("craftMatFloor", 20))]
    if config.get("autoCaveUpgrade"):
        floors.append(natural(config.get("caveMatFloor", 20)))
    if used is None or daily is None or any(value is None for value in floors):
        return result
    left, floor = min(400, daily) - used, max(floors)
    if left <= 0:
        result["reason"] = f"Đủ giới hạn quyên góp hôm nay: {used}/{min(400, daily)} cống hiến."
        return result
    # Reserve urgent quest recipes and the next major's ingredients even when
    # auto crafting is off. Missing stock for an output is NOT proof of surplus.
    reserve = Counter()
    try:
        for entry in priorities(state, config, meta):
            if entry["reason"] in URGENT_REASONS:
                for item in entry["recipe"]["inputs"]:
                    reserve[item["itemId"]] += item["qty"] * entry["count"]
        major = next_major(state, at_cap=False)
        if major:
            for item in major["materials"]:
                reserve[item["itemId"]] += item["qty"]
    except (KeyError, TypeError, ValueError, AttributeError):
        return result
    candidates = []
    for item_id, value in DONATION_VALUES.items():
        have = natural(materials.get(item_id))
        if have is None:
            continue
        held = floor + reserve[item_id]
        surplus = max(0, have - held)
        qty = min(100, surplus, left // value)
        if qty:
            candidates.append((surplus, have, item_id, qty, held, value))
    if not candidates:
        result["reason"] = "Không có vật phẩm quyên góp dư trên sàn và dự trữ nhiệm vụ/đột phá."
        return result
    surplus, have, item_id, qty, held, value = max(candidates)
    result["action"] = {"itemId": item_id, "qty": qty, "have": have, "keep": held,
                        "surplus": surplus, "gain": qty * value, "dailyLimit": min(400, daily)}
    result["reason"] = "Quyên góp loại có lượng dư nhiều nhất, không chạm sàn/dự trữ hoặc vượt hạn mức ngày."
    return result


def boss_ready(state: dict, boss: dict | None, *, now_ms: int) -> bool:
    character = state.get("character")
    level = natural(character.get("level")) if isinstance(character, dict) else None
    if level is None or level < 10 or not isinstance(boss, dict):
        return False
    hp, attempts, end = (natural(boss.get(key)) for key in ("hp", "attemptsLeft", "endsAt"))
    return (isinstance(boss.get("bossId"), str) and bool(boss["bossId"])
            and boss.get("status") == "active" and hp is not None and hp > 0
            and attempts is not None and 0 < attempts <= 3 and end is not None and end > now_ms)


def validate_state(before: dict, after: dict) -> None:
    if (type(after.get("stateVersion")) is not int or type(before.get("stateVersion")) is not int
            or after["stateVersion"] <= before["stateVersion"]):
        raise ValueError("Game chưa xác nhận stateVersion mới; dừng, không retry.")


def validate_donation(before: dict, after: dict, action: dict) -> None:
    validate_state(before, after)
    sect = after.get("sect") or {}
    if (membership_id(sect) != membership_id(before.get("sect"))
            or natural((after.get("materials") or {}).get(action["itemId"])) != action["have"] - action["qty"]
            or natural(sect.get("donatedToday")) != natural(before["sect"].get("donatedToday")) + action["gain"]):
        raise ValueError("Game chưa xác nhận đúng vật phẩm/số lượng/cống hiến quyên góp; giữ khóa.")


def validate_boss(before: dict, after: dict | None) -> None:
    if (not isinstance(after, dict) or any(after.get(key) != before.get(key) for key in ("bossId", "endsAt"))
            or natural(after.get("attemptsLeft")) != natural(before.get("attemptsLeft")) - 1):
        raise ValueError("Chưa xác nhận giảm đúng một lượt boss cùng kỳ; giữ khóa, không retry.")
