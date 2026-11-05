"""Pure, state-driven title selector. No network or account mutations.

Only an owned title can be equipped (public client ``Ed``). Titles that only
add hp/def do not increase damage, and crit titles are scored only when the
character's current crit/critDmg are known. Missing or inconsistent state never
authorizes an equip.
"""

from __future__ import annotations

import math

from api.services.craft_profession import character_build

# Sword/body skills scale with Công (atk); thunder/soul/formation skills scale
# with Công pháp thuật (matk). ``character_build`` resolves sect/weapon first.
DAMAGE_STATS = {
    "sword": "atk",
    "body": "atk",
    "thunder": "matk",
    "soul": "matk",
    "formation": "matk",
}
EPSILON = 1e-9


def number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def parse_titles(state: dict) -> dict[str, dict] | None:
    """Return validated title records, or ``None`` when the snapshot is incomplete."""
    ascend = state.get("ascend")
    if not isinstance(ascend, dict):
        return None
    raw_titles = ascend.get("titles")
    if not isinstance(raw_titles, list):
        return None
    titles: dict[str, dict] = {}
    for entry in raw_titles:
        if not isinstance(entry, dict):
            return None
        title_id = entry.get("id")
        if not isinstance(title_id, str) or not title_id or title_id in titles:
            return None
        owned, earned, equipped = entry.get("owned"), entry.get("earned"), entry.get("equipped")
        if type(owned) is not bool or type(earned) is not bool or type(equipped) is not bool:
            return None
        titles[title_id] = {"id": title_id, "owned": owned, "earned": earned, "equipped": equipped}
    return titles


def title_label(title_id: str, meta: dict) -> str:
    definition = (meta.get("titles") or {}).get(title_id) or {}
    if isinstance(definition.get("name"), str) and definition["name"]:
        return definition["name"]
    name_key = definition.get("nameKey")
    if isinstance(name_key, str) and name_key.startswith("realm."):
        realm = (meta.get("realms") or {}).get(name_key.split(".", 1)[1]) or {}
        if isinstance(realm.get("name"), str) and realm["name"]:
            return realm["name"]
    return title_id


def title_score(definition: dict, damage_stat: str, stats: dict | None) -> float | None:
    """Relative expected damage multiplier from a title, or ``None`` if unknown."""
    mods = definition.get("mods")
    if not isinstance(mods, list):
        return None
    attack_pct = 0.0
    crit_add = 0.0
    crit_dmg_add = 0.0
    for mod in mods:
        if not isinstance(mod, dict):
            return None
        stat = mod.get("stat")
        if stat in ("atk", "matk"):
            pct = number(mod.get("pct"))
            if pct is None or pct <= -1:
                return None
            if stat == damage_stat:
                attack_pct += pct
        elif stat == "crit":
            value = number(mod.get("add"))
            if value is None:
                return None
            crit_add += value
        elif stat == "critDmg":
            value = number(mod.get("add"))
            if value is None:
                return None
            crit_dmg_add += value
    score = 1.0 + attack_pct
    if crit_add or crit_dmg_add:
        if not isinstance(stats, dict):
            return None
        base_crit, base_crit_dmg = number(stats.get("crit")), number(stats.get("critDmg"))
        if base_crit is None or base_crit_dmg is None:
            return None
        before = 1.0 + base_crit * (base_crit_dmg - 1.0)
        after = 1.0 + (base_crit + crit_add) * (base_crit_dmg + crit_dmg_add - 1.0)
        if before <= 0 or after < 0:
            return None
        score *= after / before
    return score


def plan_title_equip(state: dict, config: dict, meta: dict) -> dict:
    """Plan at most one ``title.equip``; the worker re-plans after state changes."""
    result = {"phase": "ready", "action": None, "reason": "", "build": "unknown",
              "damageStat": None, "scores": {}}
    if not config.get("autoEquipTitle"):
        result["phase"], result["reason"] = "disabled", "Tự đeo danh hiệu đang tắt; không gửi lệnh game."
        return result
    try:
        build = character_build(state, config)
    except (TypeError, KeyError, ValueError):
        build = "unknown"
    result["build"] = build
    damage_stat = DAMAGE_STATS.get(build)
    result["damageStat"] = damage_stat
    if damage_stat is None:
        result["phase"] = "unknown"
        result["reason"] = "Chưa xác định được hệ nhân vật từ tông môn/vũ khí; không đoán danh hiệu tốt nhất."
        return result
    titles = parse_titles(state)
    if titles is None:
        result["phase"] = "unknown"
        result["reason"] = "Chưa có ascend.titles đầy đủ (id/owned/earned/equipped); không suy đoán."
        return result
    definitions = meta.get("titles")
    if not isinstance(definitions, dict) or not definitions:
        result["phase"] = "unknown"
        result["reason"] = "Thiếu bảng danh hiệu đã đối chiếu; không chấm điểm."
        return result

    equipped = [title for title in titles.values() if title["equipped"]]
    if len(equipped) > 1:
        result["phase"] = "unknown"
        result["reason"] = "State có nhiều danh hiệu đang mang; không xác định được danh hiệu hiện tại."
        return result
    current = equipped[0] if equipped else None
    owned = [title for title in titles.values() if title["owned"]]
    unknown_owned = [title["id"] for title in owned if title["id"] not in definitions]
    if unknown_owned:
        result["phase"] = "unknown"
        result["reason"] = f"Có danh hiệu chưa có trong bảng đã đối chiếu: {unknown_owned[0]}."
        return result
    if current and not current["owned"]:
        result["phase"] = "unknown"
        result["reason"] = "Danh hiệu đang mang không còn thuộc sở hữu; không tự thay."
        return result
    if not owned:
        result["reason"] = "Chưa sở hữu danh hiệu nào; không gửi lệnh."
        return result

    stats = state.get("stats")
    scores: dict[str, float] = {}
    for title in owned:
        score = title_score(definitions[title["id"]], damage_stat, stats)
        if score is None:
            result["phase"] = "unknown"
            result["reason"] = ("Thiếu crit/critDmg hoặc dữ liệu mods để chấm danh hiệu "
                                f"{title['id']}; không đoán.")
            return result
        scores[title["id"]] = score
    result["scores"] = {title_id: round(score, 6) for title_id, score in scores.items()}

    order = {title_id: index for index, title_id in enumerate(definitions)}
    best_id = min(scores, key=lambda title_id: (-scores[title_id], order.get(title_id, len(order))))
    best_score = scores[best_id]
    current_score = scores[current["id"]] if current else 1.0
    if current and current_score >= best_score - EPSILON:
        result["reason"] = (f"Danh hiệu đang mang đã tốt nhất cho hệ {build} "
                            f"({title_label(current['id'], meta)}).")
        return result
    if best_score <= 1.0 + EPSILON:
        result["reason"] = "Không có danh hiệu đã sở hữu nào tăng sát thương cho hệ này."
        return result

    result["action"] = {
        "titleId": best_id,
        "name": title_label(best_id, meta),
        "score": round(best_score, 6),
        "currentTitleId": current["id"] if current else None,
        "currentScore": round(current_score, 6),
        "build": build,
        "damageStat": damage_stat,
        "reason": f"Danh hiệu tăng sát thương cao nhất cho hệ {build}",
    }
    result["reason"] = result["action"]["reason"]
    return result


def validate_equip_response(before: dict, after: dict, title_id: str) -> None:
    """Reject an uncertain/inconsistent equip response; callers must not retry."""
    if not isinstance(after, dict):
        raise ValueError("Phản hồi đeo danh hiệu thiếu state.")
    before_version, after_version = before.get("stateVersion"), after.get("stateVersion")
    if type(after_version) is not int or type(before_version) is not int or after_version <= before_version:
        raise ValueError("Phản hồi đeo danh hiệu không tăng stateVersion; dừng, không retry.")
    before_titles, after_titles = parse_titles(before), parse_titles(after)
    if before_titles is None or after_titles is None:
        raise ValueError("Phản hồi đeo danh hiệu thiếu danh sách titles hợp lệ; dừng.")
    if title_id not in before_titles or before_titles[title_id]["owned"] is not True:
        raise ValueError("Danh hiệu mục tiêu không thuộc sở hữu trước khi đeo; dừng.")
    target = after_titles.get(title_id)
    if target is None or target["owned"] is not True:
        raise ValueError("Game không xác nhận quyền sở hữu danh hiệu mục tiêu; dừng.")
    equipped = [title["id"] for title in after_titles.values() if title["equipped"]]
    if equipped != [title_id]:
        raise ValueError("Game chưa xác nhận đúng một danh hiệu mục tiêu đang mang; dừng.")
