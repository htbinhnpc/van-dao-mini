"""Pure major-breakthrough policy, mirrored from the public client (2026-11-06).

No purchases, guessed progress, story branches, mortal choices or gate fights.
One confirmed action per tick; insurance protects major-roll exp, NOT trials.
"""

from __future__ import annotations

import time


INSURANCE = ("item_aid_thunder_ward", "item_aid_recovery_pill", "item_aid_guard_array")
CHANCES = (30, 40, 60, 100)
TOP_UP = {
    **{key: ("x2_pill_11", 85) for key in ("nguyen_anh", "hoa_than", "anh_bien", "van_dinh")},
    **{key: ("x2_pill_12", 90) for key in ("tinh_niet", "toai_niet", "khong_niet")},
    **{key: ("x2_pill_13", 95) for key in ("khong_linh", "khong_huyen", "khong_kiep", "dap_thien")},
}
EXTENDED = (("amhu", "am_hu", 1), ("duongthuc", "duong_thuc", 1),
            ("khuyniet", "khuy_niet", 4), ("tinhniet", "tinh_niet", 4),
            ("toainiet", "toai_niet", 4), ("khongniet", "khong_niet", 4),
            ("khonglinh", "khong_linh", 4), ("khonghuyen", "khong_huyen", 4),
            ("khongkiep", "khong_kiep", 4), ("dapthien", "dap_thien", 1))


def _definition(source, stage, target, materials, *, quest=None, mortal=False, gate=None, trial=True):
    return {"id": f"bt_{target}", "from": {"realmId": source, "stage": stage},
            "to": {"realmId": target, "stage": 1},
            "materials": [{"itemId": item, "qty": qty, "lossOnFail": loss} for item, qty, loss in materials],
            "requiredQuestId": quest, "requiresMortal": mortal, "gateId": gate,
            "trialId": f"trial_{target}" if trial and not gate else None}


DEFINITIONS = [
    _definition("ngung_khi", 15, "truc_co", [("item_foundation_pill", 1, False)],
                quest="q11_foundation_pill", trial=False),
    _definition("truc_co", 4, "ket_dan", [("item_core_pill", 1, False), ("item_frost_crystal", 20, True)]),
    _definition("ket_dan", 4, "nguyen_anh", [("item_nascent_pill", 1, False), ("item_ember_sand", 30, True), ("item_ancient_resin", 20, True)]),
    _definition("nguyen_anh", 4, "hoa_than", [("item_soul_pill", 1, False), ("item_moon_shard", 40, True)], mortal=True),
    _definition("hoa_than", 4, "anh_bien", [("item_transform_pill", 1, False), ("item_thunder_feather", 40, True), ("item_soul_dew", 30, True)]),
    _definition("anh_bien", 4, "van_dinh", [("item_summit_pill", 1, False), ("item_immortal_jade", 50, True), ("item_blood_iron", 40, True)]),
]
for index, (key, realm, stages) in enumerate(EXTENDED):
    previous = EXTENDED[index - 1] if index else (None, "van_dinh", 4)
    DEFINITIONS.append(_definition(previous[1], previous[2], realm,
        [(f"item_{key}_pill", 1, False), (f"item_{previous[0]}_mat" if index else "item_star_fragment", 40, True)],
        gate={"khongniet": "thien_nhan_ngu_suy", "khongkiep": "huyen_kiep"}.get(key)))


def natural(value) -> int | None:
    """Exact nonnegative integers, including the game's decimal BigInt strings."""
    if type(value) is int:
        return value if value >= 0 else None
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        try:
            return int(value)
        except ValueError:
            pass
    return None


def next_major(state: dict, *, at_cap: bool = True) -> dict | None:
    character = state.get("character")
    realm = character.get("realm") if isinstance(character, dict) else None
    if not isinstance(realm, dict):
        return None
    return next((entry for entry in DEFINITIONS if entry["from"]["realmId"] == realm.get("realmId")
                 and type(realm.get("stage")) is int and 1 <= realm["stage"] <= entry["from"]["stage"]
                 and (not at_cap or (type(realm.get("stage")) is int and realm["stage"] == entry["from"]["stage"]
                                      and character.get("next") == "major"))), None)


def roll_state(state: dict, entry: dict) -> tuple[str | None, int] | None:
    x2 = state.get("x2")
    roll = x2.get("btRoll") if isinstance(x2, dict) else None
    if (not isinstance(roll, dict) or "passed" not in roll
            or (roll["passed"] is not None and not isinstance(roll["passed"], str))
            or not isinstance(roll.get("fails"), dict)):
        return None
    fails = natural(roll["fails"].get(entry["id"], 0))
    return (roll["passed"], fails) if fails is not None else None


def loss_pct(target: str) -> int:
    if target in ("truc_co", "ket_dan"):
        return 0
    if target in ("nguyen_anh", "hoa_than"):
        return 2
    if target in ("anh_bien", "van_dinh"):
        return 3
    if target in ("am_hu", "duong_thuc", "khuy_niet", "tinh_niet", "toai_niet"):
        return 5
    return 10 if target == "dap_thien" else 8


def plan_breakthrough(state: dict, config: dict, data: dict | None = None, *, now_ms: int | None = None, meta: dict | None = None) -> dict:
    data = data or {}
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    result = {"phase": "waiting", "action": None, "reason": "", "breakthroughId": None, "chance": None}

    def wait(reason, phase="waiting"):
        result.update(reason=reason, phase=phase)
        return result

    def act(command, payload, reason):
        result.update(phase="ready", reason=reason,
                      action={"command": command, "payload": payload, "breakthroughId": entry["id"], "reason": reason})
        return result

    if not config.get("autoMajorBreakthrough"):
        return wait("Tự đột phá đại cảnh giới đang tắt.", "disabled")
    if not isinstance(data, dict) or any(state.get(key) is not None and not isinstance(state[key], dict)
                                         for key in ("x2", "dao", "ascend", "counters")):
        return wait("State/trạng thái tự động sai cấu trúc; không gửi lệnh.", "unknown")
    if data.get("majorBreakthroughPending"):
        return wait("Lần trước chưa xác nhận kết quả. Kiểm tra game; tắt và lưu auto trước khi cho phép thử lại.", "uncertain")
    if type(state.get("stateVersion")) is not int or state["stateVersion"] < 1:
        return wait("Thiếu stateVersion hợp lệ; không gửi lệnh với version suy đoán.", "unknown")
    entry = next_major(state)
    if not entry:
        return wait("Chưa ở cuối đại cảnh giới hoặc thiếu realm/stage/next đã xác nhận.")
    result["breakthroughId"] = entry["id"]
    now_last = natural(data.get("majorBreakthroughLastAttemptAt", 0))
    interval = natural(config.get("majorRetryMinutes", 30))
    if now_last is None or interval is None:
        return wait("Thiếu dữ liệu khoảng nghỉ hợp lệ.", "unknown")
    if now_last and now_ms - now_last < max(10, min(1440, interval)) * 60_000:
        return wait("Đang chờ khoảng nghỉ giữa các lần thử thách/đột phá.", "cooldown")
    quest_id = entry["requiredQuestId"]
    if quest_id:
        quests = state.get("quests")
        quest = next((q for q in quests if isinstance(q, dict) and q.get("id") == quest_id), None) if isinstance(quests, list) else None
        if quest and quest.get("status") == "claimable":
            return act("quest.claim", {"questId": quest_id}, "Nhận nhiệm vụ bắt buộc để mở đột phá")
        if not quest or quest.get("status") != "claimed":
            definitions = (meta or {}).get("quests", {})
            required_order = definitions.get(quest_id, {}).get("order", 0)
            prerequisite = next((q for q in quests if isinstance(q, dict) and q.get("status") == "claimable"
                                 and 0 < definitions.get(q.get("id"), {}).get("order", 0) < required_order), None) if isinstance(quests, list) else None
            if prerequisite:
                return act("quest.claim", {"questId": prerequisite["id"]}, "Nhận nhiệm vụ tiền đề đã hoàn thành")
            return wait(f"Chờ nhiệm vụ {quest_id}: tự luyện đan khi có đủ tài nguyên; không bỏ qua nhiệm vụ.", "quest")
    target = entry["to"]["realmId"]
    if target == "nguyen_anh":
        ch01 = (state.get("x2") or {}).get("ch01") or {}
        if not isinstance(ch01, dict) or ch01.get("branch") not in ("a", "b"):
            return wait("Cần hoàn tất chương Phá Đan Thành Anh; không tự chọn nhánh truyện.", "quest")
    if entry["requiresMortal"] and (state.get("dao") or {}).get("mortalDone") is not True:
        return wait("Cần hoàn tất ba tuyến hóa phàm; không tự chọn thay người chơi.", "quest")
    if entry["gateId"]:
        gates = (state.get("ascend") or {}).get("gates")
        gate = next((g for g in gates if isinstance(g, dict) and g.get("id") == entry["gateId"]), None) if isinstance(gates, list) else None
        total, passed = (natural(gate.get("total")), natural(gate.get("passed"))) if gate else (None, None)
        if total is None or passed is None or total < 1 or passed != total:
            return wait(f"Chờ vượt đủ cửa {entry['gateId']}; chưa tự đánh cửa Chứng đạo.", "gate")
    roll = roll_state(state, entry)
    if roll is None:
        return wait("Thiếu x2.btRoll.passed/fails hợp lệ; không đoán tỉ lệ.", "unknown")
    chance = CHANCES[min(roll[1], 3)]
    result["chance"] = chance
    minimum = natural(config.get("majorMinChance", 30))
    if minimum is None or chance < max(30, min(100, minimum)):
        return wait(f"Tỉ lệ {chance}% thấp hơn ngưỡng đã chọn; chờ, không tự thử để tăng tỉ lệ.")
    materials = state.get("materials")
    if not isinstance(materials, dict):
        return wait("Thiếu kho vật liệu đã xác nhận.", "unknown")
    for item in entry["materials"]:
        have = natural(materials.get(item["itemId"], 0))
        if have is None or have < item["qty"]:
            return wait(f"Chờ {item['itemId']} ×{item['qty']}; tự chế đan nếu đủ nguyên liệu, không tự mua.", "materials")
    character = state["character"]
    exp, need = natural(character.get("exp")), natural(character.get("expNeed"))
    if exp is None or need is None or need < 1:
        return wait("Thiếu tu vi/expNeed hợp lệ; không suy đoán.", "unknown")
    payload = {}
    if exp < need:
        top = TOP_UP.get(target)
        if not (config.get("majorAllowTopUp") and top and exp * 100 >= need * top[1]
                and (natural(materials.get(top[0], 0)) or 0) > 0):
            return wait("Chờ đủ tu vi hoặc Bổ Khuyết Đan đã cho phép ở đúng ngưỡng.", "experience")
        payload["topUp"] = True
    if entry["trialId"] and roll[0] != entry["id"]:
        return act("breakthrough.trial", {}, "Vượt thử thách đại cảnh (có thể mất vật liệu/tu vi, bảo hiểm không áp dụng)")
    if chance < 100 and loss_pct(target) > 0 and config.get("majorUseInsurance", True):
        insurance = next((item for item in INSURANCE if (natural(materials.get(item, 0)) or 0) > 0), None)
        if not insurance:
            return wait("Chờ phù/đan/trận bảo hiểm; không đột phá không bảo hiểm khi tùy chọn đang bật.", "insurance")
        payload["insurance"] = insurance
    return act("breakthrough.major", payload, f"Đột phá đại cảnh · {chance}% thành công")


def _confirmed(before: dict, after: dict) -> None:
    if (not isinstance(after, dict) or type(before.get("stateVersion")) is not int
            or type(after.get("stateVersion")) is not int or after["stateVersion"] <= before["stateVersion"]):
        raise ValueError("Phản hồi đột phá không tăng stateVersion; dừng, không retry.")
    if not isinstance(after.get("character"), dict) or any(after.get(key) is not None and not isinstance(after[key], dict)
                                                          for key in ("x2", "counters", "materials")):
        raise ValueError("Phản hồi đột phá thiếu/sai cấu trúc state.")


def validate_trial_response(before: dict, after: dict, outcome: dict) -> None:
    _confirmed(before, after)
    entry = next_major(before)
    roll = roll_state(after, entry) if entry else None
    old_roll = roll_state(before, entry) if entry else None
    if (not entry or not entry["trialId"] or not isinstance(outcome, dict)
            or type(outcome.get("trialWon")) is not bool or roll is None or old_roll is None
            or (after.get("character") or {}).get("realm") != before["character"]["realm"]):
        raise ValueError("Game chưa xác nhận kết quả thử thách/cảnh giới.")
    old_count = natural((before.get("counters") or {}).get(f"trial:{entry['id']}", 0))
    count = natural((after.get("counters") or {}).get(f"trial:{entry['id']}"))
    if (old_count is None or count != old_count + 1 or roll[1] != old_roll[1]
            or (roll[0] == entry["id"]) != outcome["trialWon"]):
        raise ValueError("Kết quả thử thách không khớp bộ đếm/btRoll; dừng.")
    _validate_materials(before, after, entry, consume_all=False, failed=not outcome["trialWon"])


def validate_major_response(before: dict, after: dict, outcome: dict, payload: dict) -> None:
    _confirmed(before, after)
    entry = next_major(before)
    old_roll = roll_state(before, entry) if entry else None
    new_roll = roll_state(after, entry) if entry else None
    if (not entry or old_roll is None or not isinstance(outcome, dict)
            or type(outcome.get("success")) is not bool):
        raise ValueError("Game chưa xác nhận kết quả đột phá.")
    realm = (after.get("character") or {}).get("realm")
    if outcome["success"]:
        if realm != entry["to"]:
            raise ValueError("Đột phá báo thành công nhưng cảnh giới chưa đổi đúng đích.")
    elif (realm != before["character"]["realm"] or new_roll is None
          or new_roll[1] != old_roll[1] + 1 or new_roll[0] == entry["id"]):
        raise ValueError("Đột phá thất bại không khớp cảnh giới/bộ đếm mới.")
    _validate_materials(before, after, entry, consume_all=outcome["success"], failed=not outcome["success"])
    if payload.get("insurance"):
        item = payload["insurance"]
        old = natural((before.get("materials") or {}).get(item))
        new = natural((after.get("materials") or {}).get(item, 0))
        if old is None or new != old - 1 or outcome.get("insurance") != item:
            raise ValueError("Game chưa xác nhận tiêu đúng bảo hiểm đột phá.")
        if not outcome["success"] and not payload.get("topUp"):
            old_exp = natural(before["character"].get("exp"))
            new_exp = natural((after.get("character") or {}).get("exp"))
            if old_exp is None or new_exp is None or new_exp < old_exp:
                raise ValueError("Kết quả bảo hiểm không xác nhận giữ tu vi.")
    if payload.get("topUp"):
        item = TOP_UP[entry["to"]["realmId"]][0]
        old = natural((before.get("materials") or {}).get(item))
        new = natural((after.get("materials") or {}).get(item, 0))
        if old is None or new != old - 1:
            raise ValueError("Game chưa xác nhận tiêu Bổ Khuyết Đan.")


def _validate_materials(before: dict, after: dict, entry: dict, *, consume_all: bool, failed: bool) -> None:
    if not isinstance(before.get("materials"), dict) or not isinstance(after.get("materials"), dict):
        raise ValueError("Phản hồi thiếu kho vật liệu để xác nhận đột phá.")
    for item in entry["materials"]:
        old = natural((before.get("materials") or {}).get(item["itemId"]))
        new = natural((after.get("materials") or {}).get(item["itemId"], 0))
        cost = item["qty"] if consume_all else item["qty"] * 20 // 100 if failed and item["lossOnFail"] else 0
        if old is None or new != old - cost:
            raise ValueError("Phản hồi chưa xác nhận đúng lượng vật liệu đột phá/thử thách.")
