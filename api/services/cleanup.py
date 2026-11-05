"""Keep the equipped loadout, not one spare per definition. Pure planner."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RARITIES = ("pham", "linh", "huyen", "dia", "thien", "tien", "dao")
SLOTS = ("weapon", "robe", "head", "bracer", "belt", "boots", "ring", "pendant")


class CleanupRules(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    mode: Literal["salvage", "sell"] = "salvage"
    maxRarity: Literal["pham", "linh", "huyen", "dia", "thien", "tien", "dao"] = "dao"
    maxTier: int = Field(default=0, ge=0, le=99)
    # Accepted for old saved configs/clients; no longer reserves bag copies.
    keepPerDefinition: int = Field(default=0, ge=0, le=10)
    maxItems: int = Field(default=20, ge=1, le=60)
    slots: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("keepPerDefinition")
    @classmethod
    def no_spares(cls, value: int) -> int:
        return 0

    @field_validator("slots")
    @classmethod
    def known_slots(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value) or any(slot not in SLOTS for slot in value):
            raise ValueError("Vị trí trang bị không hợp lệ hoặc bị lặp.")
        return value


def config_rules(config: dict) -> CleanupRules:
    return CleanupRules(
        mode=config.get("cleanupMode", "salvage"),
        maxRarity=config.get("cleanupMaxRarity", "dao"),
        maxTier=config.get("cleanupMaxTier", 0),
        keepPerDefinition=0,
        maxItems=config.get("cleanupMaxItems", 20),
        slots=config.get("cleanupSlots", []),
    )


REASONS = {
    "not_bag": "Không ở trong túi (đang mặc/kho/vị trí khác)",
    "protected": "Đã khóa hoặc đánh dấu yêu thích",
    "unknown": "Thiếu dữ liệu an toàn hoặc metadata/chỉ số chưa hỗ trợ",
    "enhanced": "Cường hóa cao hơn món đang mặc; chưa chuyển được hết",
    "empty_slot": "Chưa có món đang mặc hợp lệ ở ô này",
    "filter": "Ngoài bộ lọc phẩm chất/cấp đồ/vị trí",
    "limit": "Để lại cho mẻ sau vì giới hạn số món",
}


def _whole(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    try:
        result = int(value)
        return result if result >= 0 else None
    except (ValueError, OverflowError):
        return None


def _vector(item: dict, stats: dict) -> dict[str, Decimal] | None:
    known = {"id", "defId", "slot", "location", "enhance", "subs", "locked", "favorite", "createdAt", "updatedAt", "created_at", "updated_at"}
    if set(item) - known:
        return None  # Future sockets/affixes/bindings must be reviewed, not ignored.
    enhance = _whole(item.get("enhance"))
    if enhance is None or not isinstance(item.get("subs"), list):
        return None
    result = {"enhance": Decimal(enhance)}
    for modifier in item["subs"]:
        if (not isinstance(modifier, dict) or not isinstance(modifier.get("stat"), str) or modifier["stat"] not in stats
                or set(modifier) - {"stat", "add", "pct"} or not ({"add", "pct"} & set(modifier))):
            return None
        for kind in ("add", "pct"):
            if kind not in modifier:
                continue
            raw = modifier[kind]
            if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
                return None
            try:
                value = Decimal(str(raw))
            except InvalidOperation:
                return None
            if not value.is_finite() or abs(value) > Decimal("1e30"):
                return None
            key = f"{kind}:{modifier['stat']}"
            result[key] = result.get(key, Decimal(0)) + value
    return result


def plan_cleanup(state: dict, rules: CleanupRules, meta: dict) -> dict:
    equipment = state.get("equipment")
    if not isinstance(equipment, list):
        equipment = []
    rows = [item for item in equipment if isinstance(item, dict)]
    counts = Counter(item.get("id") for item in rows if isinstance(item.get("id"), str))
    worn = {}
    for slot in SLOTS:
        matches = [item for item in rows if item.get("location") == "equipped" and item.get("slot") == slot]
        if len(matches) == 1:
            item = matches[0]
            definition = meta.get("equipment", {}).get(item.get("defId")) if isinstance(item.get("defId"), str) else None
            if (isinstance(item.get("id"), str) and counts[item["id"]] == 1 and definition
                    and definition.get("slot") == slot and _vector(item, meta.get("stats", {})) is not None):
                worn[slot] = item
    reasons: Counter = Counter()
    if len(rows) < len(equipment):
        reasons["unknown"] += len(equipment) - len(rows)
    kept: list[dict] = []
    candidates: list[dict] = []
    for item in rows:
        item_id = item.get("id")
        definition = meta.get("equipment", {}).get(item.get("defId")) if isinstance(item.get("defId"), str) else None
        reason = None
        vector = _vector(item, meta.get("stats", {}))
        if not isinstance(item_id, str) or not item_id or counts[item_id] != 1 or not definition or vector is None:
            reason = "unknown"
        elif item.get("location") != "bag":
            reason = "not_bag"
        elif item.get("locked") is True or item.get("favorite") is True:
            reason = "protected"
        elif item.get("locked") is not False or item.get("favorite") is not False:
            reason = "unknown"
        elif (item.get("slot") != definition.get("slot") or definition.get("slot") not in SLOTS
              or definition.get("rarity") not in RARITIES or _whole(definition.get("tier")) is None):
            reason = "unknown"
        elif item.get("slot") not in worn:
            reason = "empty_slot"
        elif _whole(item.get("enhance")) > _whole(worn[item["slot"]].get("enhance")):
            reason = "enhanced"
        elif (RARITIES.index(definition["rarity"]) > RARITIES.index(rules.maxRarity)
              or (rules.maxTier and _whole(definition["tier"]) > rules.maxTier)
              or (rules.slots and definition["slot"] not in rules.slots)):
            reason = "filter"
        row = {
            "id": item_id, "defId": item.get("defId"), "name": definition.get("name", item_id) if definition else str(item_id or "Không rõ"),
            "slot": definition.get("slot") if definition else None,
            "rarity": definition.get("rarity") if definition else None,
            "tier": definition.get("tier") if definition else None,
            "enhance": item.get("enhance"), "subs": item.get("subs", []),
            "reason": reason,
        }
        if reason:
            reasons[reason] += 1
            kept.append({**row, "reasonLabel": REASONS[reason]})
        else:
            candidates.append({**row, "reason": "not_equipped", "reasonLabel": "Không mặc; giữ món đang trang bị cùng ô", "keptItemId": worn[item["slot"]]["id"]})
    selected, deferred = candidates[:rules.maxItems], candidates[rules.maxItems:]
    for row in deferred:
        kept.append({**row, "reason": "limit", "reasonLabel": REASONS["limit"]})
        reasons["limit"] += 1
    return {
        "rules": rules.model_dump(), "stateVersion": state.get("stateVersion"),
        "items": selected, "kept": kept, "scanned": len(equipment),
        "candidateCount": len(candidates), "deferredCount": len(deferred),
        "summary": [{"reason": reason, "label": REASONS[reason], "count": count} for reason, count in reasons.items()],
    }
