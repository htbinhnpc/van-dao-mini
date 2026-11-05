"""Prepare cleanup via official equip.best / item.transfer, never guessed scores."""

from collections import Counter
from typing import Awaitable, Callable

from api.services.cleanup import SLOTS, _vector, _whole


class PreparationError(ValueError):
    def __init__(self, state: dict, message: str):
        super().__init__(message)
        self.state = state


def validate_equipment_response(current: dict, result: dict, name: str, payload: dict) -> None:
    if (not isinstance(result, dict) or type(result.get("stateVersion")) is not int
            or result["stateVersion"] <= current.get("stateVersion", 0)
            or not isinstance(result.get("equipment"), list)):
        raise ValueError("Game chưa xác nhận state trang bị mới; dừng trước khi dọn.")
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


async def prepare_equipment(state: dict, meta: dict, send: Callable[[dict, str, dict, str], Awaitable[dict]]) -> dict:
    """Choose the game's loadout, then transfer the highest spare enhance per slot.

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
