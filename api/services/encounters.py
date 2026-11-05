"""Kỳ ngộ (secret-realm encounters): choose the choice that gives the most cảm ngộ (insight).

Source: public game client (i18n-DxMaxujG.js, declaration ``pi``; UI text on the Bí cảnh
page: an encounter appears about every 400 hunting cycles and up to 3 wait for a choice).
These are client-side observations, not server guarantees. Command:
``POST /api/cmd/encounter.resolve`` with ``{encounterId, choice}``; ``state.encounters`` is a
list of ``{id, defId}``. Choices may have a ``cost`` that is paid from materials/wallet.
"""

from __future__ import annotations

import math
from typing import Any

# defId -> minimum level and choices {id: {insight, stones, items, cost}}
ENCOUNTERS: dict[str, dict[str, Any]] = {
    "enc_wounded_crane": {"name": "Hạc bị thương", "minLevel": 1, "choices": {
        "a": {"insight": 8, "items": {"item_qi_pill": 2}, "cost": {"item_spirit_herb": 5}},
        "b": {"stones": 60}}},
    "enc_old_stele": {"name": "Bia đá cũ", "minLevel": 5, "choices": {
        "a": {"insight": 12},
        "b": {"items": {"item_iron_ore": 12}}}},
    "enc_lost_merchant": {"name": "Thương nhân lạc đường", "minLevel": 8, "choices": {
        "a": {"stones": 300},
        "b": {"items": {"item_qi_pill": 4}, "cost": {"spirit_stone": 100}}}},
    "enc_sealed_cave": {"name": "Động phủ bỏ hoang", "minLevel": 16, "choices": {
        "a": {"insight": 20},
        "b": {"items": {"item_frost_crystal": 10}}}},
    "enc_dying_cultivator": {"name": "Tu sĩ hấp hối", "minLevel": 20, "choices": {
        "a": {"insight": 35, "cost": {"item_spirit_pill": 1}},
        "b": {"stones": 4000}}},
    "enc_moonlit_duel": {"name": "Kiếm ảnh dưới trăng", "minLevel": 25, "choices": {
        "a": {"insight": 30},
        "b": {"items": {"item_moon_shard": 10}}}},
}


def _number(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def have(state: dict, item_id: str) -> float:
    """Amount owned: materials first, then wallet currencies (e.g. spirit_stone)."""
    materials, wallet = state.get("materials") or {}, state.get("wallet") or {}
    return _number(materials.get(item_id, wallet.get(item_id)))


def affordable(state: dict, choice: dict) -> bool:
    return all(have(state, item) >= qty for item, qty in (choice.get("cost") or {}).items())


def pick_choice(defn: dict | None, state: dict, *, allow_cost: bool = True) -> str | None:
    """Best choice id: most insight first (paid options only when allowed and affordable),
    otherwise the best free choice; None when the encounter is unknown or nothing is possible."""
    if not defn:
        return None
    options = [(cid, c) for cid, c in defn["choices"].items()
               if (allow_cost or not c.get("cost")) and affordable(state, c)]
    if not options:
        return None
    # Rank: insight, then free over paid, then stones, then item count. Ties keep game order.
    def score(option):
        _, c = option
        return (c.get("insight", 0), not c.get("cost"), c.get("stones", 0), sum((c.get("items") or {}).values()))
    return max(options, key=score)[0]


def plan(state: dict, *, allow_cost: bool = True, limit: int = 3) -> list[tuple[str, str, str]]:
    """Resolve plan as (encounterId, choiceId, defId) for waiting encounters, at most ``limit``."""
    out = []
    for entry in state.get("encounters") or []:
        if not isinstance(entry, dict) or not isinstance(entry.get("id"), str) or not entry["id"]:
            continue
        defn = ENCOUNTERS.get(entry.get("defId"))
        if not defn:
            continue  # unknown (new) encounter: never guess a choice
        choice = pick_choice(defn, state, allow_cost=allow_cost)
        if choice:
            out.append((entry["id"], choice, entry["defId"]))
        if len(out) >= limit:
            break
    return out
