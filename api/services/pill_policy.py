"""Realm-aware cultivation pill bands.

The game has three stackable cultivation buffs but does not expose a formal
"pill band" field. Keep one reviewed table here so the use and craft paths
cannot drift apart:

- Ngưng Khí / Trúc Cơ (realm order 1-2, level 1-19) -> Dưỡng Khí Đan
- Kết Đan / Nguyên Anh (realm order 3-4, level 20-27) -> Tụ Linh Đan
- Hóa Thần and above (realm order 5+, level 28+) -> Đại Tụ Linh Đan

Only metadata is used. Missing/unknown realms fall back to the character level;
nothing is inferred from the inventory.
"""

from __future__ import annotations

# Ordered from the lowest to the highest band. "level" is the exclusive upper
# bound used only when the realm is missing/unknown.
PILL_BANDS = (
    {"index": 0, "maxRealmOrder": 2, "level": 20,
     "itemId": "item_qi_pill", "recipeId": "recipe_qi_pill"},
    {"index": 1, "maxRealmOrder": 4, "level": 28,
     "itemId": "item_spirit_pill", "recipeId": "recipe_spirit_pill"},
    {"index": 2, "maxRealmOrder": None, "level": None,
     "itemId": "item_grand_pill", "recipeId": "recipe_grand_pill"},
)

ITEM_BAND = {band["itemId"]: band["index"] for band in PILL_BANDS}


def _realm_order(character: dict, meta: dict) -> int | None:
    realm = character.get("realm") if isinstance(character, dict) else None
    realm_id = realm.get("realmId") if isinstance(realm, dict) else realm if isinstance(realm, str) else None
    definition = (meta.get("realms") or {}).get(realm_id) if isinstance(realm_id, str) else None
    order = definition.get("order") if isinstance(definition, dict) else None
    return order if type(order) is int and order > 0 else None


def pill_band_index(character: dict, meta: dict) -> int:
    """Return the highest band allowed for the current realm (0..2)."""
    order = _realm_order(character, meta)
    if order is not None:
        for band in PILL_BANDS:
            if band["maxRealmOrder"] is None or order <= band["maxRealmOrder"]:
                return band["index"]
    level = character.get("level") if isinstance(character, dict) else None
    level = level if type(level) is int and level > 0 else 1
    for band in PILL_BANDS:
        if band["level"] is None or level < band["level"]:
            return band["index"]
    return len(PILL_BANDS) - 1


def pill_band(character: dict, meta: dict) -> dict:
    """Return the current band plus the display name from item metadata."""
    band = dict(PILL_BANDS[pill_band_index(character or {}, meta or {})])
    item = ((meta or {}).get("items") or {}).get(band["itemId"]) or {}
    band["name"] = item.get("name", band["itemId"])
    return band


def item_band_index(item_id: str) -> int | None:
    return ITEM_BAND.get(item_id)
