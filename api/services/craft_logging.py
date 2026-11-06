"""Small, credential-free craft decision snapshots for UI and activity logs."""

from __future__ import annotations

from copy import deepcopy


SETTINGS = {
    "autoCraft": False, "autoMajorBreakthrough": False, "craftMastery": True, "craftProduce": True,
    "craftLevelOrder": "fastest", "craftLevelDaily": 20, "craftReserveStones": 1000, "craftMatFloor": 20,
    "craftInsuranceKeep": 30, "craftQiTarget": 10, "craftCharmTarget": 2, "craftKeepQty": 10,
    "craftRecipeId": "", "craftBuild": "auto", "majorUseInsurance": True, "majorAllowTopUp": False,
}
PROFESSIONS = {"alchemy": "Luyện đan", "forging": "Rèn khí", "talisman": "Chế phù", "array": "Trận pháp"}
BUILD_NAMES = {"auto": "Tự nhận hệ", "sword": "Kiếm tu", "body": "Thể tu", "thunder": "Lôi tu", "soul": "Hồn tu", "formation": "Trận tu", "unknown": "Chưa xác định"}


def on(value) -> str:
    return "bật" if value is True else "tắt" if value is False else "chưa rõ"


def amount(value) -> str:
    return f"{value:,}".replace(",", ".") if type(value) is int else "chưa rõ"


def diagnostics(plan: dict, state: dict, config: dict, data: dict, meta: dict, *, active_config: dict | None = None) -> dict:
    """Whitelist settings, never copy arbitrary config/account/state into logs."""
    settings = {key: config.get(key, default) for key, default in SETTINGS.items()}
    active = active_config or config
    if active.get("_majorPreparationOnly"):
        settings["autoCraft"] = active.get("_autoCraftSetting", settings["autoCraft"])
    scope = "major_only" if active.get("_majorPreparationOnly") else "full" if settings["autoCraft"] else "disabled"
    budget = plan["budget"]
    resources = plan.get("resources", {})
    recipe_id = settings["craftRecipeId"]
    pinned = meta.get("recipes", {}).get(recipe_id, {}).get("name", recipe_id) if isinstance(recipe_id, str) else "chưa rõ"
    setting_lines = [
        f"Tự chế tạo: {on(settings['autoCraft'])}; auto đại cảnh: {on(settings['autoMajorBreakthrough'])}; phạm vi: "
        + {"major_only": "chỉ chuẩn bị đại cảnh, không cày nghề/sản xuất", "full": "đủ luồng ưu tiên → cày nghề → sản xuất", "disabled": "không gửi lệnh"}[scope],
        f"Cày tay nghề: {on(settings['craftMastery'])}; sản xuất sau max: {on(settings['craftProduce'])}; thứ tự: "
        + ("nghề còn lâu tới max nhất (ETA ước tính)" if settings["craftLevelOrder"] == "all-max-first" else "nhanh lên cấp kế nhất"),
        f"Ngân sách cày/ngày: {settings['craftLevelDaily']}%; giữ {amount(settings['craftReserveStones'])} linh thạch; sàn nguyên liệu: {settings['craftMatFloor']}/loại",
        f"Mục tiêu: Dưỡng Khí Đan {settings['craftQiTarget']}; trận kỳ {settings['craftCharmTarget']}; trần sản xuất {settings['craftKeepQty']}; trần bùa/trận bảo hiểm {settings['craftInsuranceKeep']}",
        f"Hệ cài đặt: {BUILD_NAMES.get(settings['craftBuild'], 'Chưa rõ')}; hệ đã nhận: {BUILD_NAMES.get(plan['build'], 'Chưa rõ')}; công thức ghim: {pinned or 'không ghim'}",
        f"Đại cảnh: yêu cầu bảo hiểm {on(settings['majorUseInsurance'])}; cho phép Bổ Khuyết Đan {on(settings['majorAllowTopUp'])}",
    ]
    resource_lines = [
        f"Lò: {plan['freeSlots']}/{plan['slots']} trống; {len(plan['jobs'])} mẻ đang chạy" + ("; dữ liệu lò chưa đầy đủ" if resources.get("furnacesKnown") is False else ""),
        f"Ví: {amount(resources.get('stones'))} linh thạch; giữ cấu hình {amount(settings['craftReserveStones'])}; giữ thêm đầu vào ưu tiên {amount(resources.get('priorityStones', 0))}",
        f"Ngân sách cày UTC {budget['day']}: trần {amount(budget['limit'])}, đã dùng/giữ chỗ {amount(budget['spent'])}, còn {amount(budget['remaining'])}",
    ]
    focus = data.get("craftLevelFocus")
    focus = {key: focus.get(key) for key in ("profession", "level")} if isinstance(focus, dict) else None
    if focus:
        resource_lines.append(f"Nghề đang tập trung: {PROFESSIONS.get(focus['profession'], 'Chưa rõ')} cấp {focus['level']}; đổi lựa chọn sau khi lên cấp")
    decision = plan.get("decision", "ready" if plan["action"] else "waiting")
    next_step = plan.get("nextStep")
    if not next_step:
        if plan["action"]:
            action = plan["action"]
            next_step = f"Dự kiến {action['name']} ×{action['count']} ({amount(action['stones'])} linh thạch); worker kiểm tra lại và chờ game xác nhận đủ mẻ, không tự retry."
        elif plan["blocked"]:
            samples = {}
            for entry in plan["blocked"]:
                samples.setdefault(entry.get("profession") or entry["name"], entry)
            next_step = "Không gửi lệnh. Xử lý chốt chặn: " + "; ".join(f"{PROFESSIONS.get(key, key)}: {entry.get('nextStep', entry['reason'])}" for key, entry in list(samples.items())[:4])
        else:
            next_step = "Chờ vòng tiếp theo; không tự mua nguyên liệu hoặc thay đổi cấu hình."
    return {
        "schema": "craft_diagnostics_v1", "decision": decision, "reason": plan["reason"], "nextStep": next_step,
        "settings": settings, "scope": scope, "settingLines": setting_lines, "resourceLines": resource_lines,
        "resources": resources, "budget": budget, "focus": focus, "stateVersion": state.get("stateVersion"),
        "professions": plan["professions"], "selection": plan.get("selection", []),
        "blocked": plan["blocked"][:40], "blockedTotal": plan.get("blockedTotal", len(plan["blocked"])),
        "blockSummary": plan.get("blockSummary", []), "productionSkipped": plan.get("productionSkipped", {}),
    }


def audit(plan: dict, status: str, *, runtime: dict | None = None, next_step: str | None = None) -> dict:
    result = deepcopy(plan["diagnostics"])
    result["status"] = status
    if runtime is not None:
        result["runtime"] = runtime
    if next_step:
        result["nextStep"] = next_step
    return result


def message(plan: dict) -> str:
    """Keep the headline short; full settings/constraints remain in details."""
    detail = plan["diagnostics"]
    scope = {"full": "đầy đủ", "major_only": "chỉ đại cảnh", "disabled": "đang tắt"}[detail["scope"]]
    config = detail["settings"]
    return (f"{plan['reason']} · Phạm vi {scope}; cày {on(config['craftMastery'])}, sản xuất {on(config['craftProduce'])}; "
            f"lò {plan['freeSlots']}/{plan['slots']}; ngân sách cày còn {amount(plan['budget']['remaining'])}. "
            f"Tiếp: {detail['nextStep']}")
