"""Pure, resource-bounded profession planner. No network or account mutations.

Policy adapted from craft-professions.md. Only explicit next=null means max.
Future mastery thresholds are estimates for ETA, never authorization to spend.
"""

from __future__ import annotations

import math
import time
from collections import Counter
from datetime import datetime, timezone

from api.services.breakthrough import CHANCES, INSURANCE, TOP_UP, loss_pct, natural, next_major, roll_state
from api.services.craft_logging import diagnostics
from api.services.pill_policy import item_band_index, pill_band

PROFESSIONS = {"alchemy": "Luyện đan", "forging": "Rèn khí", "talisman": "Chế phù", "array": "Trận pháp"}
CRAFTED_TO_REACH = (0, 3, 8, 15, 25, 40, 60, 85, 115, 150)
MASTERY_RECIPES = {"alchemy": "recipe_qi_pill", "forging": "recipe_iron_sword",
                   "talisman": "recipe_aid_thunder_ward", "array": "recipe_aid_guard_array"}
BREAKTHROUGH = dict(zip(
    ("ngung_khi", "truc_co", "ket_dan", "nguyen_anh", "hoa_than", "anh_bien", "van_dinh", "am_hu", "duong_thuc", "khuy_niet", "tinh_niet", "toai_niet", "khong_niet", "khong_linh", "khong_huyen", "khong_kiep"),
    ("recipe_foundation_pill", "recipe_core_pill", "recipe_nascent_pill", "recipe_soul_pill", "recipe_transform_pill", "recipe_summit_pill", "recipe_amhu_pill", "recipe_duongthuc_pill", "recipe_khuyniet_pill", "recipe_tinhniet_pill", "recipe_toainiet_pill", "recipe_khongniet_pill", "recipe_khonglinh_pill", "recipe_khonghuyen_pill", "recipe_khongkiep_pill", "recipe_dapthien_pill")))
SECT_BUILDS = {"sect_thanh_van": "sword", "sect_loi_dinh": "thunder", "sect_thiet_son": "body", "sect_hon_dang": "soul", "sect_cam_van": "formation"}
WEAPON_BUILDS = {"weapon": "sword", "staff": "thunder", "gauntlet": "body", "lantern": "soul", "banner": "formation"}
CULTIVATION_CHARMS = {"x2_talisman_05": 5, "charm_arr_tu_linh": 10}
UNLOCK_DUNGEONS = {f"x2_recipe_{n:03}": f"x2_dungeon_{(n - 31) // 2 + 1:02}" for n in range(31, 51)}
URGENT_REASONS = {"Nhiệm vụ đang làm", "Đan đột phá đại cảnh kế tiếp", "Bảo hiểm đột phá đại cảnh", "Bổ Khuyết Đan đột phá"}


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
    major = next_major(state, at_cap=False) if config.get("autoMajorBreakthrough") else None
    if config.get("_majorPreparationOnly") and not major:
        return result
    required = (meta.get("quests", {}).get((major or {}).get("requiredQuestId")) or {}).get("order", 0)
    def add(recipe_id: str, needed: int, reason: str, batches: bool = False):
        recipe = recipes.get(recipe_id)
        if recipe and needed > 0:
            count = needed if batches else math.ceil(max(0, needed - owned_output(state, recipe)) / output_qty(recipe, state))
            if count:
                result.append({"recipe": recipe, "count": count, "reason": reason, "target": None if batches else needed})

    for quest in state.get("quests") or []:
        if not isinstance(quest, dict) or quest.get("status") != "active":
            continue
        if config.get("_majorPreparationOnly") and not (required and 0 < meta.get("quests", {}).get(quest.get("id"), {}).get("order", 0) <= required):
            continue
        if config.get("_majorPreparationOnly") and natural(quest.get("current")) is None:
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
    if major:
        target = major["to"]["realmId"]
        roll = roll_state(state, major)
        if config.get("majorUseInsurance", True) and loss_pct(target) > 0 and roll and CHANCES[min(roll[1], 3)] < 100:
            options = [r for r in recipes.values() if (r.get("output") or {}).get("itemId") in INSURANCE]
            # The three aids are interchangeable; stock/queued output of any one
            # is enough. Cheapest currently affordable aid first, never all three.
            if not any(owned_output(state, r) > 0 for r in options):
                options = [r for r in options if integer(r.get("reqLevel")) <= integer(character.get("level"))]
                options.sort(key=lambda r: (any(integer((state.get("materials") or {}).get(i["itemId"])) < integer(i["qty"]) for i in r.get("inputs", [])), integer(r.get("stones")), integer(r.get("durationMs")), r["id"]))
                if options:
                    add(options[0]["id"], 1, "Bảo hiểm đột phá đại cảnh")
        top = TOP_UP.get(target)
        if config.get("majorAllowTopUp") and top:
            exp, need = natural(character.get("exp")), natural(character.get("expNeed"))
            if exp is not None and need and exp < need and exp * 100 >= need * top[1]:
                recipe = next((r for r in recipes.values() if (r.get("output") or {}).get("itemId") == top[0]), None)
                if recipe:
                    add(recipe["id"], 1, "Bổ Khuyết Đan đột phá")
    if config.get("_majorPreparationOnly"):
        return result
    if config.get("craftRecipeId"):
        add(config["craftRecipeId"], integer(config.get("craftKeepQty", 999)) or 1, "Công thức ưu tiên đã chọn")
    band = pill_band(character, meta)
    add(band["recipeId"], integer(config.get("craftQiTarget", 10)), f"Bổ sung {band['name']} theo cảnh giới")
    charms = [r for r in recipes.values() if (r.get("output") or {}).get("itemId") in CULTIVATION_CHARMS and integer(r.get("reqLevel")) <= integer(character.get("level"))]
    if charms:
        best = max(charms, key=lambda r: CULTIVATION_CHARMS[r["output"]["itemId"]])
        add(best["id"], integer(config.get("craftCharmTarget", 2)), "Trận kỳ tăng tu luyện")
    return result


def plan_crafting(state: dict, config: dict, meta: dict, data: dict | None = None, *, now_ms: int | None = None) -> dict:
    """Plan the next command. Worker re-plans after every confirmed state."""
    data = data or {}
    requested_config = config
    if config.get("autoMajorBreakthrough") and not config.get("autoCraft"):
        config = {**config, "autoCraft": True, "_majorPreparationOnly": True, "_autoCraftSetting": False}
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
    band = pill_band(state.get("character") or {}, meta)
    result = {"phase": "breakthrough" if config.get("_majorPreparationOnly") else "production" if all_max else "leveling" if all(ps.values()) else "unknown", "slots": slots, "freeSlots": free,
              "budget": budget, "build": character_build(state, config), "professions": [], "action": None,
              "pillBand": band,
              "reason": "", "blocked": [], "jobs": [{**j, "name": recipes.get(j["recipeId"], {}).get("name", j["recipeId"]),
               "reason": (data.get("craftJobs") or {}).get(str(j.get("id")), {}).get("reason", "Lò đang chạy theo state game")} for j in jobs]}
    result["resources"] = {"stones": natural((state.get("wallet") or {}).get("spirit_stone")),
                           "furnacesKnown": valid and natural(crafting.get("slots")) is not None,
                           "priorityStones": 0, "priorityMaterials": {}, "directMaterials": {}}
    result.update(blockedTotal=0, blockSummary=[], selection=[], productionSkipped={})
    issues: dict = {}
    seen_blocks: set = set()

    def finish(decision: str | None = None, next_step: str | None = None) -> dict:
        if decision:
            result["decision"] = decision
        if next_step:
            result["nextStep"] = next_step
        result["diagnostics"] = diagnostics(result, state, requested_config, data, meta, active_config=config)
        result["nextStep"] = result["diagnostics"]["nextStep"]
        return result

    def record_block(recipe: dict, reason: str, *, name: str | None = None):
        key = (recipe["id"], issues.get("mode"), issues.get("code"))
        if key in seen_blocks:
            return
        seen_blocks.add(key)
        result["blockedTotal"] += 1
        entry = {"name": name or recipe.get("name", recipe["id"]), "recipeId": recipe["id"],
                 "recipeName": recipe.get("name", recipe["id"]), "profession": profession(recipe),
                 "reason": reason, **issues}
        if len(result["blocked"]) < 40 and sum(row.get("profession") == entry["profession"] for row in result["blocked"]) < 8:
            result["blocked"].append(entry)
        group = next((group for group in result["blockSummary"] if group["profession"] == entry["profession"] and group["code"] == entry.get("code")), None)
        if group:
            group["count"] += 1
        else:
            result["blockSummary"].append({"profession": entry["profession"], "code": entry.get("code"), "count": 1, "sample": entry["name"], "reason": reason})
    for key, name in PROFESSIONS.items():
        p, recipe = ps[key], recipes.get(MASTERY_RECIPES[key])
        result["professions"].append({"id": key, "name": name, **(p or {}), "known": p is not None,
                                      "pending": pending[key], "nextEtaMs": time_to_next_level(p, recipe, slots, pending[key]) if p and recipe else None,
                                      "maxEtaMs": time_to_max(p, recipe, slots) if p and recipe else None})
    if not config.get("autoCraft"):
        result["phase"], result["reason"] = "disabled", "Tự chế tạo đang tắt; xem tiến độ không gửi lệnh game."
        return finish("disabled", "Bật Tự chế tạo và lưu nếu muốn luyện tay nghề/sản xuất; xem tiến độ không tự bật hay gửi lệnh.")
    if config.get("autoMajorBreakthrough") and data.get("majorBreakthroughPending"):
        result["reason"] = "Đột phá/chế tạo lần trước chưa xác nhận; đang khóa chuẩn bị, không retry."
        return finish("uncertain", "Kiểm tra game và đồng bộ lò; tắt rồi lưu auto đại cảnh để xác nhận mở khóa, không tự retry mẻ chưa rõ kết quả.")
    if config.get("autoMajorBreakthrough") and (type(state.get("stateVersion")) is not int or state["stateVersion"] < 1):
        result["reason"] = "Thiếu stateVersion hợp lệ; chưa được phép chuẩn bị đột phá."
        return finish("unknown", "Đồng bộ lò để lấy stateVersion mới; không gửi lệnh với version suy đoán.")
    if config.get("autoMajorBreakthrough") and (not isinstance(state.get("materials"), dict)
                                                or any(natural(value) is None for value in state["materials"].values())):
        result["reason"] = "Chưa có kho vật liệu hợp lệ để chuẩn bị đột phá; không đoán tồn kho."
        return finish("unknown", "Đồng bộ game để đọc lại số lượng vật liệu; chưa gửi lệnh chế tạo.")
    if not free:
        result["reason"] = "Lò đang bận hoặc thiếu dữ liệu lò hợp lệ."
        return finish("waiting_furnaces" if valid and slots else "unknown", "Chờ mẻ đang chạy hoàn tất rồi game kết toán; bấm Đồng bộ lò để cập nhật." if valid and slots else "Đồng bộ lò để đọc đủ slots/jobs hợp lệ; không đoán là có lò trống.")
    priority = priorities(state, config, meta)
    floor = integer(config.get("craftMatFloor", 20))
    reserve_materials: Counter = Counter()
    major = next_major(state, at_cap=False) if config.get("autoMajorBreakthrough") else None
    direct_reserve = {item["itemId"]: item["qty"] for item in major["materials"]} if major else {}
    reserve_stones = 0
    for entry in priority:
        if entry["reason"] not in URGENT_REASONS:
            continue
        for item in entry["recipe"].get("inputs", []):
            reserve_materials[item["itemId"]] += integer(item.get("qty")) * entry["count"]
        reserve_stones += integer(entry["recipe"].get("stones")) * entry["count"]
    result["resources"].update(priorityStones=reserve_stones, priorityMaterials=dict(reserve_materials), directMaterials=direct_reserve)

    def available(recipe: dict, *, filler: bool, target: int | None = None, mastery: bool = False, urgent: bool = False) -> tuple[int, str]:
        issues.clear()
        issues["mode"] = "mastery" if mastery else "priority" if urgent else "replenishment_or_production"

        def block(code: str, reason: str, next_step: str, **details):
            issues.update(code=code, nextStep=next_step, details=details)
            return 0, reason

        if (any(type(recipe.get(field)) is not int or recipe[field] < 0 for field in ("durationMs", "reqLevel", "stones"))
                or recipe["durationMs"] < 1 or not isinstance(recipe.get("inputs"), list)
                or profession(recipe) is None):
            return block("recipe_unknown", "Metadata công thức chưa đầy đủ", "Cập nhật/đồng bộ metadata công thức; chưa được phép tiêu tài nguyên.")
        if integer((state.get("character") or {}).get("level")) < integer(recipe["reqLevel"]):
            have = integer((state.get("character") or {}).get("level"))
            return block("level", f"Chưa đủ cấp mở công thức: cấp {have}, cần {recipe['reqLevel']}", f"Tu luyện tới cấp {recipe['reqLevel']} để mở công thức.", have=have, need=recipe["reqLevel"])
        dungeon = UNLOCK_DUNGEONS.get(recipe["id"])
        cleared = ((state.get("x2") or {}).get("dungeon") or {}).get("firstCleared", [])
        if dungeon and dungeon not in cleared:
            return block("dungeon", f"Chưa vượt bí cảnh mở công thức: {dungeon}", f"Vượt {dungeon} lần đầu rồi đồng bộ game; Mini không tự mua quyền mở.", dungeonId=dungeon)
        count = min(free, 8)
        if recipe.get("weekLimit") is not None:
            used = crafting.get("weekUsed")
            if not isinstance(used, dict):
                return block("weekly_unknown", "Thiếu bộ đếm giới hạn tuần", "Đồng bộ lò để đọc weekUsed, không giả định còn lượt.", limit=recipe["weekLimit"])
            count = min(count, max(0, integer(recipe["weekLimit"]) - integer(used.get(recipe["id"]))))
            if not count:
                return block("weekly_limit", f"Đã hết lượt chế tạo tuần: dùng {integer(used.get(recipe['id']))}/{recipe['weekLimit']}", "Chờ game làm mới giới hạn tuần.", used=integer(used.get(recipe["id"])), limit=recipe["weekLimit"])
        stones = max(0, integer((state.get("wallet") or {}).get("spirit_stone")) - integer(config.get("craftReserveStones", 1000)) - (reserve_stones if filler else 0))
        cost = integer(recipe["stones"])
        if mastery:
            stones = min(stones, budget["remaining"])
        if cost:
            count = min(count, stones // cost)
            if not count:
                have = integer((state.get("wallet") or {}).get("spirit_stone"))
                reserves = integer(config.get("craftReserveStones", 1000)) + (reserve_stones if filler else 0)
                daily = mastery and budget["remaining"] < cost
                reason = (f"Hết ngân sách cày ngày: còn {budget['remaining']}, cần {cost}/mẻ" if daily else
                          f"Chạm mức linh thạch dự trữ: ví {have} − giữ {reserves} = {max(0, have - reserves)}, cần {cost}/mẻ")
                return block("daily_budget" if daily else "stones", reason,
                             "Chờ ngày UTC mới hoặc chủ động điều chỉnh ngân sách cày/ngày trong Tự động; không hoàn lại lượt giữ chỗ chưa xác nhận." if daily else
                             f"Tích lũy thêm linh thạch để ví còn ít nhất {reserves + cost}, hoặc chủ động xem lại mức dự trữ; Mini không tự hạ dự trữ.",
                             have=have, reserve=reserves, available=stones, need=cost, dailyRemaining=budget["remaining"] if mastery else None)
        inputs: Counter = Counter()
        for item in recipe["inputs"]:
            if not isinstance(item, dict) or not isinstance(item.get("itemId"), str) or type(item.get("qty")) is not int or item["qty"] < 1:
                return block("inputs_unknown", "Nguyên liệu công thức không hợp lệ", "Cập nhật/đồng bộ công thức; chưa gửi lệnh.")
            inputs[item["itemId"]] += item["qty"]
        missing = []
        for item_id, quantity in inputs.items():
            have = integer((state.get("materials") or {}).get(item_id))
            held = (0 if urgent else floor) + (reserve_materials[item_id] if filler else 0) + direct_reserve.get(item_id, 0)
            available_qty = max(0, have - held)
            count = min(count, available_qty // quantity)
            if available_qty < quantity:
                missing.append({"itemId": item_id, "name": meta.get("items", {}).get(item_id, {}).get("name", item_id),
                                "have": have, "floor": 0 if urgent else floor, "priorityReserve": reserve_materials[item_id] if filler else 0,
                                "breakthroughReserve": direct_reserve.get(item_id, 0), "available": available_qty, "need": quantity,
                                "requiredTotal": held + quantity, "missing": held + quantity - have})
        if missing:
            why = "; ".join(f"{item['name']}: có {item['have']}, giữ {item['requiredTotal'] - item['need']}, dùng được {item['available']}/{item['need']}, thiếu {item['missing']}" for item in missing)
            return block("materials", f"Thiếu nguyên liệu dư trên sàn dự trữ — {why}", "Tích lũy thêm nguyên liệu theo số thiếu; giữ sàn và đầu vào ưu tiên/đột phá, không tự mua hoặc hạ mức giữ.", materials=missing)
        output = recipe["output"]
        each = output_qty(recipe, state)
        if output["kind"] == "equip":
            capacity = integer(state.get("bagCapacity"))
            equipment = state.get("equipment")
            if not isinstance(equipment, list) or any(not isinstance(e, dict) or e.get("location") not in ("bag", "equipped", "vault") for e in equipment):
                return block("bag_unknown", "Chưa đủ dữ liệu sức chứa túi; tạm ngừng Rèn khí", "Đồng bộ túi đồ để đọc bagCapacity/equipment hợp lệ.")
            bag_used = sum(e.get("location") == "bag" for e in equipment)
            reserved = sum(output_qty(recipes[j["recipeId"]], state) for j in jobs if j["recipeId"] in recipes and recipes[j["recipeId"]]["output"]["kind"] == "equip")
            if not capacity or (bag_used + reserved) * 10 >= capacity * 9:
                return block("bag_full" if capacity else "bag_unknown", f"Túi ≥ 90% hoặc chưa biết sức chứa; tạm ngừng Rèn khí (túi {bag_used}, thành phẩm chờ {reserved}, sức chứa {capacity or 'chưa rõ'})",
                             "Kiểm tra/dọn túi hoặc mở thêm sức chứa, rồi đồng bộ; các mẻ đang chạy vẫn giữ chỗ trong túi." if capacity else "Đồng bộ túi để xác nhận sức chứa trước khi rèn.",
                             used=bag_used, pendingOutput=reserved, capacity=capacity, outputPerBatch=each)
            count = min(count, max(0, math.ceil(capacity * .9) - bag_used - reserved) // each)
            if not count:
                return block("bag_full", f"Chỗ túi còn dưới ngưỡng 90% không đủ cho {each} thành phẩm/mẻ (đã dùng {bag_used}, lò giữ {reserved}, sức chứa {capacity})",
                             "Dọn đủ chỗ cho toàn bộ thành phẩm gồm bonus tay nghề rồi đồng bộ lại.", used=bag_used, pendingOutput=reserved, capacity=capacity, outputPerBatch=each)
        else:
            item = meta.get("items", {}).get(output.get("itemId"))
            if not item:
                return block("output_unknown", "Chưa biết thành phẩm", "Cập nhật/đồng bộ metadata thành phẩm; chưa chế tạo.")
            cap = integer(item.get("stackCap"))
            if recipe["id"] in ("recipe_aid_thunder_ward", "recipe_aid_guard_array"):
                cap = min(cap, integer(config.get("craftInsuranceKeep", 999)))
            if target is not None:
                cap = min(cap, target)
            count = min(count, max(0, cap - owned_output(state, recipe)) // each)
            if not count:
                have = owned_output(state, recipe)
                return block("stock", f"Đã đủ tồn kho hoặc lò đang chạy sẽ lấp đầy mục tiêu: có/dự kiến {have}, trần {cap}, mỗi mẻ +{each}",
                             "Chờ dùng bớt thành phẩm; chỉ đổi trần tồn kho nếu thực sự muốn sản xuất thêm.", ownedAndPending=have, cap=cap, outputPerBatch=each)
        return count, ""

    def choose(recipe: dict, count: int, phase: str, reason: str) -> dict:
        result["action"] = {"recipeId": recipe["id"], "name": recipe.get("name", recipe["id"]), "profession": profession(recipe),
                            "count": count, "phase": phase, "reason": reason, "stones": integer(recipe["stones"]) * count,
                            "durationMs": batch_ms(recipe, (ps.get(profession(recipe)) or {}).get("level", 1))}
        result["reason"] = reason
        return finish(phase)

    for entry in priority:
        recipe = entry["recipe"]
        if all_max and any(j["recipeId"] == recipe["id"] for j in jobs):
            issues.clear(); issues.update(code="recipe_running", mode="priority", nextStep="Chờ lò cùng công thức đang chạy hoàn tất; không xếp trùng sau khi max nghề.")
            record_block(recipe, "Công thức đã có lò đang chạy; không xếp trùng sau khi max nghề")
            continue
        urgent = entry["reason"] in URGENT_REASONS
        count, reason = available(recipe, filler=not urgent, urgent=urgent, target=None if urgent else entry["target"])
        if count:
            return choose(recipe, min(count, entry["count"], 1 if all_max else 8), "priority", entry["reason"])
        record_block(recipe, reason)
    if config.get("_majorPreparationOnly"):
        result["reason"] = "Chờ lò/tài nguyên cho đột phá; không cày nghề hay sản xuất ngoài luồng khi Tự chế tạo đang tắt."
        return finish("waiting_breakthrough")
    if not all(ps.values()):
        result["reason"] = "Chưa đủ dữ liệu 4 tay nghề; không suy đoán nghề đã max."
        missing_professions = [PROFESSIONS[key] for key, value in ps.items() if value is None]
        return finish("unknown", f"Đồng bộ đủ level/crafted/next cho: {', '.join(missing_professions)}; chưa coi là max hay bắt đầu sản xuất.")
    if not all_max:
        if not config.get("craftMastery", True):
            result["reason"] = "Cày tay nghề đang tắt; sản xuất chỉ bắt đầu khi cả 4 nghề max."
            return finish("mastery_disabled", "Bật Cày tay nghề và lưu nếu muốn tự luyện nghề; sản xuất chỉ mở khi cả 4 nghề có next=null từ game.")
        focus = data.get("craftLevelFocus") or {}
        candidates = []
        for key, p in ps.items():
            if p["maxed"]:
                continue
            # Once enough batches for this level are queued, wait for settlement.
            if pending[key] and pending[key] >= p["next"] - p["crafted"]:
                result["reason"] = f"Chờ {PROFESSIONS[key]} hoàn tất các mẻ đã đủ lên cấp kế."
                return finish("waiting_level", f"Chờ {pending[key]} mẻ {PROFESSIONS[key]} hoàn tất và game kết toán lên cấp; sau đó tính lại nghề ưu tiên, không xếp vượt mốc.")
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
                record_block(recipe, reason, name=PROFESSIONS[key])
            if not options:
                result["blocked"].append({"name": PROFESSIONS[key], "profession": key, "code": "no_recipe", "reason": "Không có công thức phù hợp", "nextStep": "Đồng bộ metadata công thức cho nghề này."})
        if candidates:
            _, _, key, recipe, count = min(candidates, key=lambda c: c[:3])
            result["selection"] = [{"profession": candidate[2], "name": PROFESSIONS[candidate[2]], "recipeId": candidate[3]["id"], "recipeName": candidate[3].get("name", candidate[3]["id"]),
                                    "count": candidate[4], "focused": not candidate[0], "selected": candidate[2] == key,
                                    "etaMs": abs(candidate[1]), "estimateTo": "max" if config.get("craftLevelOrder") == "all-max-first" else "next"}
                                   for candidate in sorted(candidates, key=lambda c: c[:3])]
            return choose(recipe, count, "mastery", f"Dồn lò cày {PROFESSIONS[key]} cấp {ps[key]['level']} → cấp kế")
        result["reason"] = "Các nghề chưa max đều bị chặn bởi cấp, tài nguyên, ngân sách hoặc tồn kho."
        return finish("blocked")
    if not config.get("craftProduce", True):
        result["reason"] = "Cả 4 nghề đã max; sản xuất đang tắt."
        return finish("production_disabled", "Bật Sản xuất sau khi max và lưu nếu muốn dùng lò trống; không tự thay đổi tùy chọn này.")
    used_recipes = {j["recipeId"] for j in jobs}
    production = []
    def skipped(code):
        result["productionSkipped"][code] = result["productionSkipped"].get(code, 0) + 1
    for recipe in recipes.values():
        if recipe["id"] in used_recipes:
            skipped("recipe_running")
            continue
        output = recipe.get("output") or {}
        item = meta.get("items", {}).get(output.get("itemId"), {})
        use = item.get("use") or {}
        value = 0
        skip_reason = "unsupported_output"
        rate = integer((state.get("character") or {}).get("rateMilli")) / 1000
        if use.get("type") == "cultivation_buff":
            rank = item_band_index(output.get("itemId"))
            if rank is not None and rank > band["index"]:
                skip_reason = "pill_band_above_current"
            else:
                value = rate * integer(use.get("ratePct")) / 100 * integer(use.get("durationMs")) / 1000
                skip_reason = "cultivation_rate_unknown_or_zero"
        elif use.get("type") == "cultivation_exp":
            # Only the highest unlocked pill band is appropriate for this level.
            unlocked = [r for r in recipes.values() if (meta.get("items", {}).get((r.get("output") or {}).get("itemId"), {}).get("use") or {}).get("type") == "cultivation_exp" and integer(r.get("reqLevel")) <= integer((state.get("character") or {}).get("level"))]
            if unlocked and integer(recipe.get("reqLevel")) == max(integer(r.get("reqLevel")) for r in unlocked):
                value = integer(use.get("exp"))
            skip_reason = "exp_band_not_current"
        elif output.get("itemId") in CULTIVATION_CHARMS:
            value = rate * CULTIVATION_CHARMS[output["itemId"]] / 100 * 120 * 60
            skip_reason = "cultivation_rate_unknown_or_zero"
        elif output.get("kind") == "equip":
            definition = meta.get("equipment", {}).get(output.get("defId"), {})
            suffix = str(definition.get("id", "")).rsplit("_", 1)[-1]
            skip_reason = ("not_weapon" if definition.get("slot") != "weapon" else "weapon_build_unreviewed" if suffix not in WEAPON_BUILDS
                           else "build_unknown" if result["build"] == "unknown" else "build_mismatch" if WEAPON_BUILDS[suffix] != result["build"]
                           else "weapon_already_owned" if owned_output(state, recipe) else "weapon_tier_not_higher")
            # Metadata lacks x2 weapon archetypes / combat simulation: skip guesses.
            if definition.get("slot") == "weapon" and WEAPON_BUILDS.get(suffix) == result["build"] and not owned_output(state, recipe):
                worn = [meta.get("equipment", {}).get(e.get("defId"), {}) for e in state.get("equipment", []) if isinstance(e, dict) and e.get("slot") == "weapon" and e.get("location") == "equipped"]
                current = worn[0] if len(worn) == 1 else {}
                if not current or integer(definition.get("tier")) > integer(current.get("tier")):
                    value = 1  # Same-build, higher-tier only; not a guessed damage estimate.
        if not value:
            skipped(skip_reason)
        if value:
            count, reason = available(recipe, filler=True, target=integer(config.get("craftKeepQty", 999)))
            if count:
                production.append((value / batch_ms(recipe, ps[profession(recipe)]["level"]), recipe))
            else:
                record_block(recipe, reason)
    if production:
        recipe = max(production, key=lambda c: (c[0], c[1]["id"]))[1]
        return choose(recipe, 1, "production", "Sản xuất: mỗi lò một công thức khác nhau, hợp cấp/hệ tu")
    result["reason"] = "Đã đủ tồn kho, thiếu tài nguyên dư hoặc chưa có công thức hợp cấp/hệ tu. Không suy đoán giá chợ."
    return finish("blocked" if result["blocked"] else "waiting_policy", None if result["blocked"] else "Kiểm tra mục tiêu tồn kho/hệ tu/công thức ưu tiên. Chỉ sản xuất món hợp chính sách, không tự rèn hệ khác hay đoán giá chợ.")
