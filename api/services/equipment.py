"""Prepare gear using enhancement-normalized comparisons, without guessed weights."""

import re
from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Awaitable, Callable

from api.services.cleanup import SLOTS, _vector, _whole

# Public client nn / Wo / Go (i18n-B6UHPwZV.js). Rarity variants inherit tags.
X2_WEAPON_BUILDS = {f"x2_eq_{number:03}": build for number, build in (
    (1, "sword"), (9, "thunder"), (17, "body"), (25, "formation"), (33, "sword"),
    (41, "sword"), (49, "sword"), (57, "sword"), (65, "sword"), (73, "sword"),
    (81, "sword"), (89, "thunder"), (91, "sword"), (95, "sword"), (96, "sword"))}
TIER_COST = (0, 1, 2, 8, 30, 110, 400, 1400, 5000, 18000, 60000, 200000, 700000)
X2_BANDS = (16, 20, 24, 28, 32, 36, 42, 50, 58, 66)
X2_CURRENCY = (1000, 3000, 8000, 20000, 50000, 120000, 300000, 800000, 2000000, 5000000)


def weapon_build(definition: dict) -> str | None:
    base = re.sub(r"_q(?:pham|linh|huyen|dia|thien|tien|dao)$", "", definition.get("id", ""))
    if base in X2_WEAPON_BUILDS:
        return X2_WEAPON_BUILDS[base]
    match = re.fullmatch(r"equip_t\d+_(weapon|staff|gauntlet|lantern|banner)", base)
    return {"weapon": "sword", "staff": "thunder", "gauntlet": "body", "lantern": "soul", "banner": "formation"}.get(match[1]) if match else None


def enhanced_vector(item: dict, meta: dict, enhance: int | None = None) -> dict[str, Decimal] | None:
    """Client Vs: only main scales; additive/pct subs stay separate and unchanged."""
    definition = meta.get("equipment", {}).get(item.get("defId")) if isinstance(item.get("defId"), str) else None
    vector = _vector(item, meta.get("stats", {}))
    if not definition or vector is None or definition.get("cm") or "cm" in definition.get("tags", []):
        return None
    if not re.match(r"^(equip_t\d+_|x2_eq_\d+)", definition.get("id", "")):
        return None  # No unreviewed reincarnation/proc/relic rules.
    main = definition.get("main")
    if (not isinstance(main, dict) or set(main) != {"stat", "add"} or main.get("stat") not in meta.get("stats", {})
            or isinstance(main.get("add"), bool)):
        return None
    level = _whole(item.get("enhance")) if enhance is None else _whole(enhance)
    if level is None:
        return None
    try:
        amount = Decimal(str(main["add"]))
        rate = Decimal(str(definition.get("enhancePct", ".04" if definition["id"].startswith("x2_") else ".08")))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or not rate.is_finite() or not 0 <= amount <= Decimal("1e30") or not 0 <= rate <= 1:
        return None
    vector = {key: value for key, value in vector.items() if key != "enhance"}
    key = f"add:{main['stat']}"
    vector[key] = vector.get(key, Decimal(0)) + amount * (1 + rate * level)
    return vector


def transfer_fee(definition: dict, enhance: int) -> int | None:
    """Client ku: ceil(5% of all target-currency enhance costs through +N)."""
    if definition.get("cm") or "cm" in definition.get("tags", []):
        return None
    tier, required = _whole(definition.get("tier")), _whole(definition.get("reqLevel"))
    if tier is None or required is None or tier < 1 or not 0 <= enhance <= 100:
        return None
    if definition.get("id", "").startswith("x2_"):
        band = max(1, sum(required >= gate for gate in X2_BANDS))
        unit = X2_CURRENCY[band - 1]
        total = sum((unit * n * n + 9) // 10 for n in range(1, enhance + 1))
    else:
        weight = TIER_COST[tier] if tier < len(TIER_COST) else tier
        total = 20 * weight * enhance * (enhance + 1) // 2
    return (total + 19) // 20


def _preserves_set(state: dict, old: dict, new: dict, meta: dict) -> bool:
    old_set, new_set = old.get("setId"), new.get("setId")
    if old_set == new_set:
        return True
    sets = meta.get("sets", {})
    old_meta = sets.get(old_set) or sets.get(f"set_{old_set}")
    new_meta = sets.get(new_set) or sets.get(f"set_{new_set}")
    if not old_meta or not new_meta or not isinstance(old_meta.get("bonuses"), list):
        return False
    count = 0
    for item in state.get("equipment", []):
        if not isinstance(item, dict) or item.get("location") != "equipped":
            continue
        definition = meta.get("equipment", {}).get(item.get("defId"))
        if not definition:
            return False
        count += definition.get("setId") == old_set
    for bonus in old_meta["bonuses"]:
        pieces = _whole(bonus.get("pieces")) if isinstance(bonus, dict) else None
        if not pieces or count == pieces:
            return False  # Removing one piece would lose an active bonus.
    return True


def plan_normalized_upgrade(state: dict, meta: dict, slot: str) -> dict | None:
    """Find a strict per-stat improvement after simulating transferable enhance.

    No scoring tradeoffs: no stat may decrease, no active set bonus may be lost,
    and weapon archetype must stay unchanged. Never mutate real item instances.
    """
    equipment = state.get("equipment")
    level = _whole((state.get("character") or {}).get("level"))
    if not isinstance(equipment, list) or level is None:
        return None
    rows = [item for item in equipment if isinstance(item, dict)]
    counts = Counter(item.get("id") for item in rows if isinstance(item.get("id"), str))
    valid = [item for item in rows if isinstance(item.get("id"), str) and counts[item["id"]] == 1
             and item.get("slot") == slot and enhanced_vector(item, meta) is not None
             and item.get("locked") is False and item.get("favorite") is False]
    worn = [item for item in rows if item.get("slot") == slot and item.get("location") == "equipped"]
    if len(worn) != 1 or worn[0] not in valid:
        return None
    current = best = worn[0]
    definitions = meta["equipment"]
    current_def = definitions[current["defId"]]
    for candidate in valid:
        if candidate.get("location") != "bag":
            continue
        definition, best_def = definitions[candidate["defId"]], definitions[best["defId"]]
        required = _whole(definition.get("reqLevel"))
        if (definition.get("slot") != slot or current_def.get("slot") != slot or required is None or level < required
                or enhancement_cap(definition, state, meta) < _whole(current["enhance"])
                or not _preserves_set(state, current_def, definition, meta)):
            continue
        if slot == "weapon" and (not weapon_build(current_def) or weapon_build(definition) != weapon_build(current_def)):
            continue
        common = max(_whole(current["enhance"]), _whole(best["enhance"]), _whole(candidate["enhance"]))
        if enhancement_cap(definition, state, meta) < common:
            continue
        old_vector = enhanced_vector(best, meta, max(_whole(best["enhance"]), min(common, enhancement_cap(best_def, state, meta))))
        new_vector = enhanced_vector(candidate, meta, common)
        keys = old_vector.keys() | new_vector.keys()
        if all(new_vector.get(key, 0) >= old_vector.get(key, 0) for key in keys) and any(new_vector.get(key, 0) > old_vector.get(key, 0) for key in keys):
            best = candidate
    if best is current:
        return None
    definition = definitions[best["defId"]]
    donors = [item for item in valid if item is not best and item.get("location") in {"bag", "equipped"}
              and definitions[item["defId"]].get("slot") == slot
              and _whole(best["enhance"]) < _whole(item["enhance"]) <= enhancement_cap(definition, state, meta)]
    donor = max(donors, key=lambda item: _whole(item["enhance"])) if donors else None
    common = max(_whole(current["enhance"]), _whole(best["enhance"]), _whole(donor["enhance"]) if donor else 0)
    old_vector = enhanced_vector(current, meta, max(_whole(current["enhance"]), min(common, enhancement_cap(current_def, state, meta))))
    new_vector = enhanced_vector(best, meta, common)
    keys = old_vector.keys() | new_vector.keys()
    if not (all(new_vector.get(key, 0) >= old_vector.get(key, 0) for key in keys)
            and any(new_vector.get(key, 0) > old_vector.get(key, 0) for key in keys)):
        return None  # Ordinary/x2 growth can cross over at a higher donor level.
    fee = transfer_fee(definition, _whole(donor["enhance"])) if donor else 0
    stones = _whole((state.get("wallet") or {}).get("spirit_stone"))
    return {"itemId": best["id"], "previousItemId": current["id"], "slot": slot,
            "fromId": donor["id"] if donor else None, "enhance": _whole(donor["enhance"]) if donor else _whole(best["enhance"]),
            "fee": fee, "affordable": fee == 0 or (fee is not None and stones is not None and stones >= fee)}


class PreparationError(ValueError):
    def __init__(self, state: dict, message: str):
        super().__init__(message)
        self.state = state


def validate_equipment_response(current: dict, result: dict, name: str, payload: dict) -> None:
    if (not isinstance(result, dict) or type(result.get("stateVersion")) is not int
            or result["stateVersion"] <= current.get("stateVersion", 0)
            or not isinstance(result.get("equipment"), list)):
        raise ValueError("Game chưa xác nhận state trang bị mới; dừng trước khi dọn.")
    if name == "equip":
        def stable(row):
            return {key: value for key, value in row.items() if key not in {"updatedAt", "updated_at"}}

        def rows(snapshot):
            items = snapshot["equipment"]
            ids = [item.get("id") for item in items if isinstance(item, dict)]
            if len(ids) != len(items) or any(not isinstance(item_id, str) for item_id in ids) or len(set(ids)) != len(ids):
                raise ValueError("Phản hồi mặc đồ thiếu món hoặc trùng ID.")
            return {item["id"]: item for item in items}
        before, after = rows(current), rows(result)
        target = before.get(payload["itemId"])
        if not target or target.get("location") != "bag" or set(before) != set(after):
            raise ValueError("Game chưa xác nhận đúng món mục tiêu từ túi.")
        slot = target.get("slot")
        worn = [item["id"] for item in after.values() if item.get("slot") == slot and item.get("location") == "equipped"]
        if worn != [target["id"]]:
            raise ValueError("Game chưa xác nhận món mục tiêu là món duy nhất đang mặc cùng ô.")
        for item_id, old in before.items():
            new = after[item_id]
            location = "equipped" if item_id == target["id"] else "bag" if old.get("slot") == slot and old.get("location") == "equipped" else old.get("location")
            if stable(new) != stable({**old, "location": location}):
                raise ValueError("Phản hồi mặc đồ làm đổi chỉ số/vị trí ngoài bước đã yêu cầu.")
    if name == "item.transfer":
        def item(snapshot: dict, item_id: str) -> dict:
            matches = [row for row in snapshot.get("equipment", []) if isinstance(row, dict) and row.get("id") == item_id]
            if len(matches) != 1 or _whole(matches[0].get("enhance")) is None:
                raise ValueError("Phản hồi chuyển cường hóa thiếu món hoặc trùng ID.")
            return matches[0]

        source, target = item(current, payload["fromId"]), item(current, payload["toId"])
        after_source, after_target = item(result, payload["fromId"]), item(result, payload["toId"])
        if (after_target.get("location") != "equipped" or after_source.get("location") != "bag"
                or after_target.get("slot") != target.get("slot") or after_source.get("slot") != source.get("slot")
                or _whole(after_target["enhance"]) != _whole(source["enhance"])
                or _whole(after_source["enhance"]) != _whole(target["enhance"])):
            raise ValueError("Game chưa xác nhận chuyển đủ cường hóa; không dọn.")


def enhancement_cap(definition: dict, state: dict, meta: dict) -> int:
    maximum = _whole(definition.get("maxEnhance")) or 0
    if definition.get("cm"):
        return 0  # Different incarnation rules have not been reviewed.
    if not definition.get("id", "").startswith("x2_") and "x2" not in definition.get("tags", []):
        return maximum
    level = _whole((state.get("character") or {}).get("level")) or 0
    start, cap = 1, 0
    gates = {"truc_co": 5, "nguyen_anh": 10, "khuy_niet": 15, "khong_niet": 20}
    realms = sorted((r for r in meta.get("realms", {}).values() if isinstance(r.get("order"), int)), key=lambda r: r["order"])
    for realm in realms:
        if start <= level and realm.get("id") in gates:
            cap = gates[realm["id"]]
        start += realm.get("stageCount", 0)
    return min(maximum, cap)


async def prepare_equipment(state: dict, meta: dict, send: Callable[[dict, str, dict, str], Awaitable[dict]],
                            *, ensure_budget: Callable[[int], None] | None = None) -> dict:
    """Choose native loadout, correct enhancement bias, then transfer enhance.

    send must audit intent and persist each confirmed state. Any uncertain response
    aborts preparation, so its caller must NOT continue to disposal.
    """
    async def command(name: str, payload: dict, label: str) -> None:
        nonlocal state
        result = await send(state, name, payload, label)
        validate_equipment_response(state, result, name, payload)
        state = result

    try:
        if not isinstance(state.get("equipment"), list):
            raise ValueError("State thiếu danh sách trang bị.")
        if any(isinstance(item, dict) and item.get("location") == "bag" for item in state["equipment"]):
            await command("equip.best", {}, "Mặc trang bị mạnh nhất theo bộ chọn của game")
        for slot in SLOTS:
            upgrade = plan_normalized_upgrade(state, meta, slot)
            if upgrade:
                if not upgrade["affordable"]:
                    raise ValueError("Có đồ tốt hơn sau khi giả lập cường hóa nhưng chưa đủ dữ liệu/phí chuyển; giữ đồ, không dọn.")
                if ensure_budget:
                    ensure_budget(2 if upgrade["fromId"] else 1)
                await command("equip", {"itemId": upgrade["itemId"]},
                              f"Đổi đồ tốt hơn sau khi so cùng mức cường hóa +{upgrade['enhance']}")
                if upgrade["fromId"]:
                    await command("item.transfer", {"fromId": upgrade["fromId"], "toId": upgrade["itemId"]},
                                  f"Chuyển +{upgrade['enhance']} sang đồ đã chọn (phí {upgrade['fee']} linh thạch)")
            rows = [item for item in state["equipment"] if isinstance(item, dict)]
            counts = Counter(item.get("id") for item in rows if isinstance(item.get("id"), str))
            valid = [item for item in rows if isinstance(item.get("id"), str) and counts[item["id"]] == 1
                     and item.get("slot") == slot and _vector(item, meta.get("stats", {})) is not None]
            worn = [item for item in valid if item.get("location") == "equipped"]
            if len(worn) != 1 or worn[0].get("locked") is not False:
                continue
            target = worn[0]
            definition = meta.get("equipment", {}).get(target.get("defId")) if isinstance(target.get("defId"), str) else None
            if not definition or definition.get("slot") != slot:
                continue
            donors = [item for item in valid if item.get("location") == "bag" and item.get("locked") is False
                      and item.get("favorite") is False and isinstance(item.get("defId"), str)
                      and meta.get("equipment", {}).get(item["defId"], {}).get("slot") == slot
                      and _whole(item["enhance"]) > _whole(target["enhance"])]
            if not donors:
                continue
            donor = max(donors, key=lambda item: _whole(item["enhance"]))
            if _whole(donor["enhance"]) > enhancement_cap(definition, state, meta):
                continue  # Do not truncate enhance; planner retains this donor.
            await command("item.transfer", {"fromId": donor["id"], "toId": target["id"]}, "Chuyển cường hóa cao nhất sang đồ đang mặc (có phí game)")
        return state
    except Exception as exc:
        raise PreparationError(state, str(exc) or type(exc).__name__) from exc
