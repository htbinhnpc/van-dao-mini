"""Pure, resource-bounded profession planner. No network or account mutations.

Policy adapted from craft-professions.md. Only explicit next=null means max.
Future mastery thresholds are estimates for ETA, never authorization to spend.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from datetime import datetime, timezone

PROFESSIONS = {"alchemy": "Luyện đan", "forging": "Rèn khí", "talisman": "Chế phù", "array": "Trận pháp"}
CRAFTED_TO_REACH = (0, 3, 8, 15, 25, 40, 60, 85, 115, 150)
MASTERY_RECIPES = {"alchemy": "recipe_qi_pill", "forging": "recipe_iron_sword",
                   "talisman": "recipe_aid_thunder_ward", "array": "recipe_aid_guard_array"}
BREAKTHROUGH = dict(zip(
    ("ngung_khi", "truc_co", "ket_dan", "nguyen_anh", "hoa_than", "anh_bien", "van_dinh", "am_hu", "duong_thuc", "khuy_niet", "tinh_niet", "thien_nhan_ngu_suy", "khong_niet", "khong_linh", "huyen_kiep", "khong_kiep"),
    ("recipe_foundation_pill", "recipe_core_pill", "recipe_nascent_pill", "recipe_soul_pill", "recipe_transform_pill", "recipe_summit_pill", "recipe_amhu_pill", "recipe_duongthuc_pill", "recipe_khuyniet_pill", "recipe_tinhniet_pill", "recipe_toainiet_pill", "recipe_khongniet_pill", "recipe_khonglinh_pill", "recipe_khonghuyen_pill", "recipe_khongkiep_pill", "recipe_dapthien_pill")))
SECT_BUILDS = {"sect_thanh_van": "sword", "sect_loi_dinh": "thunder", "sect_thiet_son": "body", "sect_hon_dang": "soul", "sect_cam_van": "formation"}
WEAPON_BUILDS = {"weapon": "sword", "staff": "thunder", "gauntlet": "body", "lantern": "soul", "banner": "formation"}
CULTIVATION_CHARMS = {"x2_talisman_05": 5, "charm_arr_tu_linh": 10}
UNLOCK_DUNGEONS = {f"x2_recipe_{n:03}": f"x2_dungeon_{(n - 31) // 2 + 1:02}" for n in range(31, 51)}


def integer(value, default: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return default
    try:
        return max(0, int(value))
    except (ValueError, OverflowError):
        return default


def profession(recipe: dict) -> str | None:
    output = recipe.get("output") or {}
    item = output.get("itemId", "")
    if recipe.get("id") == "recipe_aid_thunder_ward" or item.startswith("charm_tal_") or item in {f"x2_talisman_{n:02}" for n in (1, 2, 3, 4, 8, 9)}:
        return "talisman"
    if recipe.get("id") == "recipe_aid_guard_array" or item.startswith("charm_arr_") or item in {"x2_talisman_05", "x2_talisman_06", "x2_talisman_07"}:
        return "array"
    return "forging" if output.get("kind") == "equip" else "alchemy" if output.get("kind") == "item" else None


def progress(state: dict, key: str) -> dict | None:
    professions = state.get("professions")
    raw = professions.get(key) if isinstance(professions, dict) else None
    if (not isinstance(raw, dict) or integer(raw.get("level")) < 1 or integer(raw.get("level")) > 100
            or integer(raw.get("crafted"), -1) < 0 or "next" not in raw):
        return None
    if raw["next"] is not None and integer(raw["next"]) <= integer(raw["crafted"]):
        return None
    return {"level": integer(raw["level"]), "crafted": integer(raw["crafted"]),
            "next": None if raw["next"] is None else integer(raw["next"]), "maxed": raw["next"] is None}


def batch_ms(recipe: dict, level: int) -> int:
    return max(1, integer(recipe.get("durationMs")) * max(1, 100 - 3 * (level - 1)) // 100)


def time_to_next_level(p: dict, recipe: dict, slots: int, pending: int = 0) -> int | None:
    if p["maxed"]:
        return 0
    if slots < 1:
        return None
    return math.ceil(max(0, p["next"] - p["crafted"] - pending) * batch_ms(recipe, p["level"]) / slots)


def time_to_max(p: dict, recipe: dict, slots: int) -> int | None:
    if p["maxed"]:
        return 0
    if slots < 1 or not 1 <= p["level"] < 10 or p["next"] > 150:
        return None
    total = max(0, p["next"] - p["crafted"]) * batch_ms(recipe, p["level"])
    for level in range(p["level"] + 1, 10):
        total += (CRAFTED_TO_REACH[level] - CRAFTED_TO_REACH[level - 1]) * batch_ms(recipe, level)
    return math.ceil(total / slots)


def output_qty(recipe: dict, state: dict) -> int:
    p = progress(state, profession(recipe))
    # Public client 2026-11-05: bonus applies to forging as well as consumables.
    bonus = p["level"] // 5 if p else 0
    return (integer((recipe.get("output") or {}).get("qty"), 1) or 1) + bonus


def owned_output(state: dict, recipe: dict) -> int:
    output = recipe["output"]
    if output["kind"] == "item":
        owned = integer((state.get("materials") or {}).get(output["itemId"]))
    else:
        owned = sum(isinstance(e, dict) and e.get("defId") == output["defId"] for e in state.get("equipment", []))
    crafting = state.get("crafting") or {}
    jobs = crafting.get("jobs") if isinstance(crafting.get("jobs"), list) else []
    return owned + sum(job.get("recipeId") == recipe["id"] for job in jobs if isinstance(job, dict)) * output_qty(recipe, state)


def daily_budget(state: dict, config: dict, data: dict, now_ms: int) -> dict:
    day = datetime.fromtimestamp(now_ms / 1000, timezone.utc).date().isoformat()
    stored = data.get("craftLevelBudget") or {}
    base = integer(stored.get("base")) if stored.get("day") == day else max(0, integer((state.get("wallet") or {}).get("spirit_stone")) - integer(config.get("craftReserveStones", 1000)))
    spent = integer(stored.get("spent")) if stored.get("day") == day else 0
    limit = base * min(100, integer(config.get("craftLevelDaily", 20))) // 100
    return {"day": day, "base": base, "limit": limit, "spent": spent, "remaining": max(0, limit - spent)}


def character_build(state: dict, config: dict) -> str:
    explicit = config.get("craftBuild", "auto")
    if explicit in WEAPON_BUILDS.values():
        return explicit
    sect = state.get("sect") or {}
    build = SECT_BUILDS.get(sect.get("id") if isinstance(sect, dict) else sect)
    if build:
        return build
    for e in state.get("equipment", []):
        if isinstance(e, dict) and e.get("slot") == "weapon" and e.get("location") == "equipped":
            for suffix, build in WEAPON_BUILDS.items():
                if str(e.get("defId", "")).endswith("_" + suffix):
                    return build
    return "unknown"


def priorities(state: dict, config: dict, meta: dict) -> list[dict]:
    recipes = meta.get("recipes", {})
    result: list[dict] = []
    def add(recipe_id: str, needed: int, reason: str, batches: bool = False):
        recipe = recipes.get(recipe_id)
        if recipe and needed > 0:
            count = needed if batches else math.ceil(max(0, needed - owned_output(state, recipe)) / output_qty(recipe, state))
            if count:
                result.append({"recipe": recipe, "count": count, "reason": reason, "target": None if batches else needed})

    for quest in state.get("quests", []):
        if not isinstance(quest, dict) or quest.get("status") != "active":
            continue
        objective = meta.get("quests", {}).get(quest.get("id"), {}).get("objective", {})
        counter = objective.get("counter", "")
        recipe_id = counter.removeprefix("craft:") if counter.startswith("craft:") else "recipe_qi_pill" if counter == "crafts_done" else ""
        if recipe_id:
            jobs = (state.get("crafting") or {}).get("jobs")
            jobs = jobs if isinstance(jobs, list) else []
            pending = sum(isinstance(job, dict) and job.get("recipeId") == recipe_id for job in jobs)
            add(recipe_id, max(0, integer(quest.get("target", objective.get("target"))) - integer(quest.get("current")) - pending), "Nhiệm vụ đang làm", True)
    character = state.get("character") or {}
    realm = character.get("realm") or {}
    realm_id = realm.get("realmId") if isinstance(realm, dict) else realm
    add(BREAKTHROUGH.get(realm_id, ""), 1, "Đan đột phá đại cảnh kế tiếp")
    if config.get("craftRecipeId"):
        add(config["craftRecipeId"], integer(config.get("craftKeepQty", 10)) or 1, "Công thức ưu tiên đã chọn")
    add("recipe_qi_pill", integer(config.get("craftQiTarget", 10)), "Bổ sung Dưỡng Khí Đan")
    charms = [r for r in recipes.values() if (r.get("output") or {}).get("itemId") in CULTIVATION_CHARMS and integer(r.get("reqLevel")) <= integer(character.get("level"))]
    if charms:
        best = max(charms, key=lambda r: CULTIVATION_CHARMS[r["output"]["itemId"]])
        add(best["id"], integer(config.get("craftCharmTarget", 2)), "Trận kỳ tăng tu luyện")
    return result


def plan_crafting(state: dict, config: dict, meta: dict, data: dict | None = None, *, now_ms: int | None = None) -> dict:
    """Plan the next command. Worker re-plans after every confirmed state."""
    data = data or {}
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    crafting = state.get("crafting") or {}
    jobs = crafting.get("jobs")
    slots = min(64, integer(crafting.get("slots")))
    valid = isinstance(jobs, list) and all(isinstance(j, dict) and isinstance(j.get("recipeId"), str) for j in jobs)
    jobs = jobs if valid else []
    free = max(0, slots - len(jobs)) if valid else 0
    recipes = meta.get("recipes", {})
    pending = Counter(profession(recipes[j["recipeId"]]) for j in jobs if j["recipeId"] in recipes)
    budget = daily_budget(state, config, data, now_ms)
    ps = {key: progress(state, key) for key in PROFESSIONS}
    all_max = all(p and p["maxed"] for p in ps.values())
    result = {"phase": "production" if all_max else "leveling" if all(ps.values()) else "unknown", "slots": slots, "freeSlots": free,
              "budget": budget, "build": character_build(state, config), "professions": [], "action": None,
              "reason": "", "blocked": [], "jobs": [{**j, "name": recipes.get(j["recipeId"], {}).get("name", j["recipeId"]),
              "reason": (data.get("craftJobs") or {}).get(str(j.get("id")), {}).get("reason", "Lò đang chạy theo state game")} for j in jobs]}
    for key, name in PROFESSIONS.items():
        p, recipe = ps[key], recipes.get(MASTERY_RECIPES[key])
        result["professions"].append({"id": key, "name": name, **(p or {}), "known": p is not None,
                                      "pending": pending[key], "nextEtaMs": time_to_next_level(p, recipe, slots, pending[key]) if p and recipe else None,
                                      "maxEtaMs": time_to_max(p, recipe, slots) if p and recipe else None})
    if not config.get("autoCraft"):
        result["phase"], result["reason"] = "disabled", "Tự chế tạo đang tắt; xem tiến độ không gửi lệnh game."
        return result
    if not free:
        result["reason"] = "Lò đang bận hoặc thiếu dữ liệu lò hợp lệ."
        return result
    priority = priorities(state, config, meta)
    floor = integer(config.get("craftMatFloor", 20))
    reserve_materials: Counter = Counter()
    reserve_stones = 0
    for entry in priority:
        if entry["reason"] not in {"Nhiệm vụ đang làm", "Đan đột phá đại cảnh kế tiếp"}:
            continue
        for item in entry["recipe"].get("inputs", []):
            reserve_materials[item["itemId"]] += integer(item.get("qty")) * entry["count"]
        reserve_stones += integer(entry["recipe"].get("stones")) * entry["count"]

    def available(recipe: dict, *, filler: bool, target: int | None = None, mastery: bool = False, urgent: bool = False) -> tuple[int, str]:
        if (any(type(recipe.get(field)) is not int or recipe[field] < 0 for field in ("durationMs", "reqLevel", "stones"))
                or recipe["durationMs"] < 1 or not isinstance(recipe.get("inputs"), list)
                or profession(recipe) is None):
            return 0, "Metadata công thức chưa đầy đủ"
        if integer((state.get("character") or {}).get("level")) < integer(recipe["reqLevel"]):
            return 0, "Chưa đủ cấp mở công thức"
        dungeon = UNLOCK_DUNGEONS.get(recipe["id"])
        cleared = ((state.get("x2") or {}).get("dungeon") or {}).get("firstCleared", [])
        if dungeon and dungeon not in cleared:
            return 0, "Chưa vượt bí cảnh mở công thức"
        count = min(free, 8)
        if recipe.get("weekLimit") is not None:
            used = crafting.get("weekUsed")
            if not isinstance(used, dict):
                return 0, "Thiếu bộ đếm giới hạn tuần"
            count = min(count, max(0, integer(recipe["weekLimit"]) - integer(used.get(recipe["id"]))))
            if not count:
                return 0, "Đã hết lượt chế tạo tuần"
        stones = max(0, integer((state.get("wallet") or {}).get("spirit_stone")) - integer(config.get("craftReserveStones", 1000)) - (reserve_stones if filler else 0))
        cost = integer(recipe["stones"])
        if mastery:
            stones = min(stones, budget["remaining"])
        if cost:
            count = min(count, stones // cost)
            if not count:
                return 0, "Hết ngân sách ngày hoặc chạm mức linh thạch dự trữ"
        inputs: Counter = Counter()
        for item in recipe["inputs"]:
            if not isinstance(item, dict) or not isinstance(item.get("itemId"), str) or type(item.get("qty")) is not int or item["qty"] < 1:
                return 0, "Nguyên liệu công thức không hợp lệ"
            inputs[item["itemId"]] += item["qty"]
        for item_id, quantity in inputs.items():
            available_qty = max(0, integer((state.get("materials") or {}).get(item_id)) - (0 if urgent else floor) - (reserve_materials[item_id] if filler else 0))
            count = min(count, available_qty // quantity)
            if not count:
                return 0, "Thiếu nguyên liệu dư trên sàn dự trữ"
        output = recipe["output"]
        each = output_qty(recipe, state)
        if output["kind"] == "equip":
            capacity = integer(state.get("bagCapacity"))
            equipment = state.get("equipment")
            if not isinstance(equipment, list) or any(not isinstance(e, dict) or e.get("location") not in ("bag", "equipped", "vault") for e in equipment):
                return 0, "Chưa đủ dữ liệu sức chứa túi; tạm ngừng Rèn khí"
            bag_used = sum(e.get("location") == "bag" for e in equipment)
            reserved = sum(output_qty(recipes[j["recipeId"]], state) for j in jobs if j["recipeId"] in recipes and recipes[j["recipeId"]]["output"]["kind"] == "equip")
            if not capacity or (bag_used + reserved) * 10 >= capacity * 9:
                return 0, "Túi ≥ 90% hoặc chưa biết sức chứa; tạm ngừng Rèn khí"
            count = min(count, max(0, math.ceil(capacity * .9) - bag_used - reserved) // each)
        else:
            item = meta.get("items", {}).get(output.get("itemId"))
            if not item:
                return 0, "Chưa biết thành phẩm"
            cap = integer(item.get("stackCap"))
            if recipe["id"] in ("recipe_aid_thunder_ward", "recipe_aid_guard_array"):
                cap = min(cap, integer(config.get("craftInsuranceKeep", 30)))
            if target is not None:
                cap = min(cap, target)
            count = min(count, max(0, cap - owned_output(state, recipe)) // each)
        return (count, "" if count else "Đã đủ tồn kho hoặc lò đang chạy sẽ lấp đầy mục tiêu")

    def choose(recipe: dict, count: int, phase: str, reason: str) -> dict:
        result["action"] = {"recipeId": recipe["id"], "name": recipe.get("name", recipe["id"]), "profession": profession(recipe),
                            "count": count, "phase": phase, "reason": reason, "stones": integer(recipe["stones"]) * count,
                            "durationMs": batch_ms(recipe, (ps.get(profession(recipe)) or {}).get("level", 1))}
        result["reason"] = reason
        return result

    for entry in priority:
        recipe = entry["recipe"]
        if all_max and any(j["recipeId"] == recipe["id"] for j in jobs):
            continue
        urgent = entry["reason"] in {"Nhiệm vụ đang làm", "Đan đột phá đại cảnh kế tiếp"}
        count, reason = available(recipe, filler=not urgent, urgent=urgent, target=None if urgent else entry["target"])
        if count:
            return choose(recipe, min(count, entry["count"], 1 if all_max else 8), "priority", entry["reason"])
        result["blocked"].append({"name": recipe.get("name", recipe["id"]), "reason": reason})
    if not all(ps.values()):
        result["reason"] = "Chưa đủ dữ liệu 4 tay nghề; không suy đoán nghề đã max."
        return result
    if not all_max:
        if not config.get("craftMastery", True):
            result["reason"] = "Cày tay nghề đang tắt; sản xuất chỉ bắt đầu khi cả 4 nghề max."
            return result
        focus = data.get("craftLevelFocus") or {}
        candidates = []
        for key, p in ps.items():
            if p["maxed"]:
                continue
            # Once enough batches for this level are queued, wait for settlement.
            if pending[key] and pending[key] >= p["next"] - p["crafted"]:
                result["reason"] = f"Chờ {PROFESSIONS[key]} hoàn tất các mẻ đã đủ lên cấp kế."
                return result
            options = sorted((r for r in recipes.values() if profession(r) == key), key=lambda r: (integer(r.get("durationMs")), r["id"]))
            for recipe in options:
                count, reason = available(recipe, filler=True, mastery=True)
                if count:
                    count = min(count, max(0, p["next"] - p["crafted"] - pending[key]))
                    eta = time_to_max(p, recipe, slots) if config.get("craftLevelOrder", "fastest") == "all-max-first" else time_to_next_level(p, recipe, slots, pending[key])
                    score = -(eta or 0) if config.get("craftLevelOrder") == "all-max-first" else eta or 0
                    locked = focus.get("profession") == key and focus.get("level") == p["level"]
                    candidates.append((not locked, score, key, recipe, count))
                    break
            else:
                result["blocked"].append({"name": PROFESSIONS[key], "reason": reason if options else "Không có công thức phù hợp"})
        if candidates:
            _, _, key, recipe, count = min(candidates, key=lambda c: c[:3])
            return choose(recipe, count, "mastery", f"Dồn lò cày {PROFESSIONS[key]} cấp {ps[key]['level']} → cấp kế")
        result["reason"] = "Các nghề chưa max đều bị chặn bởi cấp, tài nguyên, ngân sách hoặc tồn kho."
        return result
    if not config.get("craftProduce", True):
        result["reason"] = "Cả 4 nghề đã max; sản xuất đang tắt."
        return result
    used_recipes = {j["recipeId"] for j in jobs}
    production = []
    for recipe in recipes.values():
        if recipe["id"] in used_recipes:
            continue
        output = recipe.get("output") or {}
        item = meta.get("items", {}).get(output.get("itemId"), {})
        use = item.get("use") or {}
        value = 0
        rate = integer((state.get("character") or {}).get("rateMilli")) / 1000
        if use.get("type") == "cultivation_buff":
            value = rate * integer(use.get("ratePct")) / 100 * integer(use.get("durationMs")) / 1000
        elif use.get("type") == "cultivation_exp":
            # Only the highest unlocked pill band is appropriate for this level.
            unlocked = [r for r in recipes.values() if (meta.get("items", {}).get((r.get("output") or {}).get("itemId"), {}).get("use") or {}).get("type") == "cultivation_exp" and integer(r.get("reqLevel")) <= integer((state.get("character") or {}).get("level"))]
            if unlocked and integer(recipe.get("reqLevel")) == max(integer(r.get("reqLevel")) for r in unlocked):
                value = integer(use.get("exp"))
        elif output.get("itemId") in CULTIVATION_CHARMS:
            value = rate * CULTIVATION_CHARMS[output["itemId"]] / 100 * 120 * 60
        elif output.get("kind") == "equip":
            definition = meta.get("equipment", {}).get(output.get("defId"), {})
            suffix = str(definition.get("id", "")).rsplit("_", 1)[-1]
            # Metadata lacks x2 weapon archetypes / combat simulation: skip guesses.
            if definition.get("slot") == "weapon" and WEAPON_BUILDS.get(suffix) == result["build"] and not owned_output(state, recipe):
                worn = [meta.get("equipment", {}).get(e.get("defId"), {}) for e in state.get("equipment", []) if isinstance(e, dict) and e.get("slot") == "weapon" and e.get("location") == "equipped"]
                current = worn[0] if len(worn) == 1 else {}
                if not current or integer(definition.get("tier")) > integer(current.get("tier")):
                    value = 1  # Same-build, higher-tier only; not a guessed damage estimate.
        if value:
            count, reason = available(recipe, filler=True, target=integer(config.get("craftKeepQty", 10)))
            if count:
                production.append((value / batch_ms(recipe, ps[profession(recipe)]["level"]), recipe))
            else:
                result["blocked"].append({"name": recipe.get("name", recipe["id"]), "reason": reason})
    if production:
        recipe = max(production, key=lambda c: (c[0], c[1]["id"]))[1]
        return choose(recipe, 1, "production", "Sản xuất: mỗi lò một công thức khác nhau, hợp cấp/hệ tu")
    result["reason"] = "Đã đủ tồn kho, thiếu tài nguyên dư hoặc chưa có công thức hợp cấp/hệ tu. Không suy đoán giá chợ."
    return result
