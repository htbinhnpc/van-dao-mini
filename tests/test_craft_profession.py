import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.index import app
from api.routes import dashboard
from api.routes.accounts import DEFAULT_CONFIG
from api.services import automation as auto
from api.services.craft_profession import (PROFESSIONS, MASTERY_RECIPES, daily_budget, output_qty,
                                           plan_crafting, profession, progress, time_to_max, time_to_next_level)
from api.services.pill_policy import pill_band


NOW = 1793836800000


def snapshot():
    return {"stateVersion": 10, "character": {"level": 16, "realm": "unknown", "rateMilli": 2500},
            "crafting": {"slots": 4, "jobs": [], "weekUsed": {}},
            "wallet": {"spirit_stone": "1000000"}, "bagCapacity": 100, "equipment": [],
            "materials": {key: 10000 for key in ("item_spirit_herb", "item_iron_ore", "item_beast_hide", "item_frost_crystal")},
            "professions": {key: {"level": 1, "crafted": 0, "next": 3} for key in PROFESSIONS}}


def settings(**changes):
    return {**DEFAULT_CONFIG, "autoCraft": True, "craftQiTarget": 0, "craftCharmTarget": 0, **changes}


def max_all(state):
    state["professions"] = {key: {"level": 10, "crafted": 150, "next": None} for key in PROFESSIONS}
    return state


def plan(state=None, config=None, data=None, meta=None):
    return plan_crafting(state or snapshot(), config or settings(), meta or auto.META, data, now_ms=NOW)


class CraftPlannerTests(unittest.TestCase):
    def test_profession_mapping_includes_charms_and_all_four_fast_recipes(self):
        for key, recipe_id in MASTERY_RECIPES.items():
            self.assertEqual(profession(auto.META["recipes"][recipe_id]), key)
        self.assertEqual(profession(auto.META["recipes"]["x2_recipe_085"]), "array")
        self.assertEqual(profession(auto.META["recipes"]["recipe_charm_tal_kim_cang"]), "talisman")

    def test_eta_matches_document_formula_and_bonus(self):
        s = snapshot()
        for key, expected in (("alchemy", 22500), ("forging", 33750), ("talisman", 135000), ("array", 180000)):
            recipe = auto.META["recipes"][MASTERY_RECIPES[key]]
            self.assertEqual(time_to_next_level(progress(s, key), recipe, 4), expected)
        p = {"level": 5, "crafted": 25, "next": 40, "maxed": False}
        self.assertEqual(time_to_next_level(p, auto.META["recipes"]["recipe_qi_pill"], 3), 132000)
        self.assertIsNone(time_to_next_level(p, auto.META["recipes"]["recipe_qi_pill"], 0))
        total = time_to_max(progress(s, "alchemy"), auto.META["recipes"]["recipe_qi_pill"], 1)
        self.assertGreater(total, 3600000)
        self.assertLess(total, 3900000)

    def test_fastest_fills_only_one_profession_and_does_not_overshoot_next(self):
        s = snapshot(); before = copy.deepcopy(s)
        action = plan(s)["action"]
        self.assertEqual((action["recipeId"], action["count"], action["phase"]), ("recipe_qi_pill", 3, "mastery"))
        self.assertEqual(s, before)

    def test_next_level_progress_changes_fastest_profession(self):
        s = snapshot(); s["professions"]["alchemy"] = {"level": 2, "crafted": 3, "next": 8}
        self.assertEqual(plan(s)["action"]["profession"], "forging")

    def test_all_max_first_prefers_largest_remaining_work(self):
        self.assertEqual(plan(config=settings(craftLevelOrder="all-max-first"))["action"]["profession"], "array")

    def test_focus_is_sticky_until_level_changes_and_pending_covers_next_waits(self):
        data = {"craftLevelFocus": {"profession": "array", "level": 1}}
        self.assertEqual(plan(data=data)["action"]["profession"], "array")
        s = snapshot(); s["professions"]["array"] = {"level": 2, "crafted": 3, "next": 8}
        self.assertEqual(plan(s, data=data)["action"]["profession"], "alchemy")
        s = snapshot(); s["crafting"]["jobs"] = [{"id": str(i), "recipeId": "recipe_qi_pill"} for i in range(3)]
        self.assertIsNone(plan(s)["action"])
        self.assertIn("Chờ", plan(s)["reason"])

    def test_blocked_profession_is_skipped_for_an_affordable_one(self):
        s = snapshot(); s["materials"]["item_spirit_herb"] = 20
        result = plan(s)
        self.assertEqual(result["action"]["profession"], "forging")
        self.assertTrue(any(entry["name"] == "Luyện đan" for entry in result["blocked"]))

    def test_diagnostics_show_settings_block_reason_and_next_action(self):
        s = snapshot(); s["materials"]["item_spirit_herb"] = 20
        result = plan(s)
        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["schema"], "craft_diagnostics_v1")
        self.assertTrue(diagnostics["settings"]["autoCraft"])
        self.assertIn("Tự chế tạo: bật", "\n".join(diagnostics["settingLines"]))
        self.assertIn("Ngân sách cày UTC", "\n".join(diagnostics["resourceLines"]))
        entry = next(entry for entry in result["blocked"] if entry["name"] == "Luyện đan")
        self.assertEqual(entry["code"], "materials")
        self.assertIn("thiếu", entry["reason"])
        self.assertIn("Tích lũy thêm nguyên liệu", entry["nextStep"])
        self.assertIn("Dự kiến", diagnostics["nextStep"])
        self.assertIn("Tự chế tạo: bật", diagnostics["settingLines"][0])

    def test_blocked_without_action_keeps_per_profession_next_step(self):
        s = snapshot(); s["materials"] = {}
        result = plan(s)
        self.assertIsNone(result["action"])
        self.assertEqual(result["diagnostics"]["decision"], "blocked")
        self.assertIn("Xử lý chốt chặn", result["nextStep"])
        self.assertGreaterEqual(result["blockedTotal"], 4)
        self.assertTrue(result["blocked"])
        self.assertTrue(all(entry.get("nextStep") for entry in result["blocked"]))
        self.assertTrue(all(entry.get("recipeName") for entry in result["blocked"]))

    def test_disabled_diagnostics_explain_enablement_without_sending_commands(self):
        result = plan(config=settings(autoCraft=False))
        self.assertIsNone(result["action"])
        self.assertEqual(result["diagnostics"]["scope"], "disabled")
        self.assertEqual(result["decision"], "disabled")
        self.assertIn("Bật Tự chế tạo", result["nextStep"])

    def test_diagnostics_whitelist_settings_and_mark_major_only_scope(self):
        secret = settings(sessionToken="must-not-leak", autoCraft=False, autoMajorBreakthrough=True)
        result = plan(config=secret)
        diagnostics = result["diagnostics"]
        self.assertEqual(diagnostics["scope"], "major_only")
        self.assertFalse(diagnostics["settings"]["autoCraft"])
        self.assertNotIn("sessionToken", diagnostics["settings"])
        self.assertNotIn("must-not-leak", str(diagnostics))

    def test_level_daily_and_material_floor_are_enforced(self):
        s = snapshot(); s["materials"] = {"item_spirit_herb": 23}
        self.assertIsNone(plan(s)["action"])
        s["materials"]["item_spirit_herb"] = 24
        self.assertEqual(plan(s)["action"]["count"], 1)
        s["character"]["level"] = 1
        for key in ("forging", "talisman", "array"):
            s["professions"][key] = {"level": 10, "crafted": 150, "next": None}
        self.assertIsNone(plan(s)["action"])

    def test_daily_budget_is_fixed_per_day_and_survives_restarts(self):
        s = snapshot(); cfg = settings(craftLevelDaily=20)
        budget = daily_budget(s, cfg, {}, NOW)
        self.assertEqual(budget["limit"], 199800)
        data = {"craftLevelBudget": {**budget, "spent": 199790}}
        s["wallet"]["spirit_stone"] = "9999999"
        self.assertEqual(daily_budget(s, cfg, data, NOW)["remaining"], 10)
        self.assertEqual(daily_budget(s, settings(craftLevelDaily=10), data, NOW)["remaining"], 0)
        self.assertEqual(daily_budget(s, cfg, data, NOW + 86400000)["spent"], 0)

    def test_zero_budget_allows_free_mastery_but_blocks_paid_mastery(self):
        s = snapshot(); cfg = settings(craftLevelDaily=0)
        self.assertEqual(plan(s, cfg)["action"]["profession"], "alchemy")
        s["professions"]["alchemy"] = {"level": 10, "crafted": 150, "next": None}
        self.assertIsNone(plan(s, cfg)["action"])

    def test_near_full_unknown_capacity_and_pending_forging_output_block_forging(self):
        for capacity, bag_count, pending_jobs in ((100, 90, 0), (None, 0, 0), (100, 87, 1)):
            s = max_all(snapshot()); s["professions"]["forging"] = {"level": 5, "crafted": 25, "next": 40}
            s["bagCapacity"] = capacity
            s["equipment"] = [{"id": str(i), "location": "bag"} for i in range(bag_count)]
            s["crafting"]["jobs"] = [{"id": f"job{i}", "recipeId": "recipe_iron_sword"} for i in range(pending_jobs)]
            # Each level-5 forging batch produces 2 gear, not one.
            result = plan(s)
            self.assertIsNone(result["action"])

    def test_insurance_stock_cap_includes_inflight_bonus(self):
        s = max_all(snapshot()); s["professions"]["talisman"] = {"level": 5, "crafted": 25, "next": 40}
        s["materials"]["item_aid_thunder_ward"] = 29
        # All talisman recipes except insurance require absent paper/ink.
        self.assertIsNone(plan(s, settings(craftInsuranceKeep=30))["action"])
        s["materials"]["item_aid_thunder_ward"] = 28
        self.assertEqual(plan(s, settings(craftInsuranceKeep=30))["action"]["count"], 1)

    def test_unknown_professions_never_trigger_production_or_guessed_max(self):
        for changes in ({"level": 10, "crafted": 150}, {"level": 10, "crafted": 150, "next": 200}, None):
            s = max_all(snapshot()); s["professions"]["array"] = changes
            result = plan(s, settings(craftMastery=False))
            self.assertNotEqual(result["phase"], "production")
            self.assertIsNone(result["action"])

    def test_quest_then_breakthrough_then_replenishment_take_priority(self):
        s = snapshot(); s["character"]["realm"] = "ngung_khi"
        s["materials"].update({"item_wolf_king_fang": 21, "item_guardian_core": 21})
        result = plan(s)
        self.assertEqual(result["action"]["recipeId"], "recipe_foundation_pill")
        self.assertEqual(result["action"]["reason"], "Đan đột phá đại cảnh kế tiếp")
        s["quests"] = [{"id": "q05_first_craft", "status": "active", "current": 0, "target": 1}]
        self.assertEqual(plan(s)["action"]["reason"], "Nhiệm vụ đang làm")
        s["quests"] = []; s["materials"]["item_foundation_pill"] = 1
        self.assertEqual(plan(s, settings(craftQiTarget=10))["action"]["reason"], "Bổ sung Dưỡng Khí Đan theo cảnh giới")

    def test_pill_band_follows_realm_then_level_fallback(self):
        for realm, item in (("ngung_khi", "item_qi_pill"), ("truc_co", "item_qi_pill"),
                            ("ket_dan", "item_spirit_pill"), ("nguyen_anh", "item_spirit_pill"),
                            ("hoa_than", "item_grand_pill"), ("van_dinh", "item_grand_pill")):
            self.assertEqual(pill_band({"level": 1, "realm": {"realmId": realm, "stage": 1}}, auto.META)["itemId"], item)
        for level, item in ((1, "item_qi_pill"), (16, "item_qi_pill"), (19, "item_qi_pill"),
                            (20, "item_spirit_pill"), (27, "item_spirit_pill"), (28, "item_grand_pill")):
            self.assertEqual(pill_band({"level": level, "realm": "unknown"}, auto.META)["itemId"], item)

    def test_craft_target_uses_current_realm_pill(self):
        s = snapshot(); s["wallet"]["spirit_stone"] = "100000000"
        s["character"] = {"level": 16, "realm": {"realmId": "truc_co", "stage": 1}, "rateMilli": 2500}
        result = plan(s, settings(craftQiTarget=10))
        self.assertEqual(result["action"]["recipeId"], "recipe_qi_pill")
        self.assertEqual(result["pillBand"]["name"], "Dưỡng Khí Đan")
        for realm, recipe in (("ket_dan", "recipe_spirit_pill"), ("nguyen_anh", "recipe_spirit_pill")):
            s["character"] = {"level": 20, "realm": {"realmId": realm, "stage": 1}, "rateMilli": 2500}
            self.assertEqual(plan(s, settings(craftQiTarget=10))["action"]["recipeId"], recipe)
        s["materials"]["item_thunder_feather"] = 1000
        for realm in ("hoa_than", "anh_bien", "van_dinh"):
            s["character"] = {"level": 28, "realm": {"realmId": realm, "stage": 1}, "rateMilli": 2500}
            self.assertEqual(plan(s, settings(craftQiTarget=10))["action"]["recipeId"], "recipe_grand_pill")

    def test_production_never_crafts_pills_above_current_band(self):
        s = max_all(snapshot()); s["materials"]["item_thunder_feather"] = 1000
        s["character"] = {"level": 16, "realm": {"realmId": "truc_co", "stage": 1}, "rateMilli": 2500}
        result = plan(s)
        self.assertEqual(result["action"]["recipeId"], "recipe_qi_pill")
        self.assertEqual(result["productionSkipped"].get("pill_band_above_current"), 2)
        s["character"] = {"level": 28, "realm": {"realmId": "hoa_than", "stage": 1}, "rateMilli": 2500}
        self.assertNotIn("pill_band_above_current", plan(s)["productionSkipped"])

    def test_missing_critical_materials_do_not_get_spent_by_mastery(self):
        s = snapshot(); s["character"]["realm"] = "ngung_khi"
        s["materials"] = {"item_spirit_herb": 40}
        result = plan(s)
        self.assertIsNone(result["action"])

    def test_weekly_limit_is_never_exceeded_or_inferred_when_missing(self):
        meta = copy.deepcopy(auto.META)
        recipe = meta["recipes"]["recipe_qi_pill"]
        recipe["weekLimit"] = 2
        s = snapshot(); s["crafting"]["weekUsed"] = {recipe["id"]: 1}
        self.assertEqual(plan(s, meta=meta)["action"]["count"], 1)
        del s["crafting"]["weekUsed"]
        self.assertNotEqual(plan(s, meta=meta)["action"]["profession"], "alchemy")

    def test_paid_recipe_missing_declared_cost_is_not_treated_as_free(self):
        meta = copy.deepcopy(auto.META)
        meta["recipes"] = {"recipe_iron_sword": meta["recipes"]["recipe_iron_sword"]}
        del meta["recipes"]["recipe_iron_sword"]["stones"]
        self.assertIsNone(plan(meta=meta)["action"])

    def test_dungeon_gated_recipes_need_first_clear_even_when_pinned(self):
        s = max_all(snapshot()); s["character"]["level"] = 28
        recipe = auto.META["recipes"]["x2_recipe_033"]
        s["materials"].update({item["itemId"]: 100 for item in recipe["inputs"]})
        cfg = settings(craftRecipeId=recipe["id"], craftProduce=False)
        self.assertIsNone(plan(s, cfg)["action"])
        s["x2"] = {"dungeon": {"firstCleared": ["x2_dungeon_02"]}}
        self.assertEqual(plan(s, cfg)["action"]["recipeId"], recipe["id"])

    def test_breakthrough_can_use_its_rare_material_without_twenty_spares(self):
        s = snapshot(); s["character"]["realm"] = "ngung_khi"
        s["materials"].update({"item_wolf_king_fang": 1, "item_guardian_core": 1})
        self.assertEqual(plan(s)["action"]["recipeId"], "recipe_foundation_pill")

    def test_production_uses_one_batch_and_different_recipe_per_running_furnace(self):
        s = max_all(snapshot()); s["character"] = {"level": 20, "realm": {"realmId": "ket_dan", "stage": 1}, "rateMilli": 2500}
        result = plan(s)
        self.assertEqual(result["phase"], "production")
        self.assertEqual(result["action"]["count"], 1)
        recipe_id = result["action"]["recipeId"]
        s["crafting"]["jobs"] = [{"id": "job1", "recipeId": recipe_id}]
        second = plan(s)["action"]
        self.assertIsNotNone(second)
        self.assertNotEqual(second["recipeId"], recipe_id)
        self.assertEqual(second["count"], 1)

    def test_production_toggles_and_zero_stock_stop_filler(self):
        s = max_all(snapshot())
        self.assertIsNone(plan(s, settings(craftProduce=False))["action"])
        self.assertIsNone(plan(s, settings(craftKeepQty=0))["action"])
        self.assertIsNone(plan(snapshot(), settings(craftMastery=False))["action"])
        self.assertIsNone(plan(s, settings(autoCraft=False))["action"])

    def test_forging_production_matches_build_and_has_no_duplicates(self):
        meta = copy.deepcopy(auto.META)
        meta["recipes"] = {key: value for key, value in meta["recipes"].items() if key in ("recipe_frost_blade", "recipe_thunder_staff", "recipe_soul_lantern", "recipe_iron_gauntlet")}
        for build, recipe_id in (("sword", "recipe_frost_blade"), ("thunder", "recipe_thunder_staff"), ("soul", "recipe_soul_lantern"), ("body", "recipe_iron_gauntlet")):
            s = max_all(snapshot()); cfg = settings(craftBuild=build)
            self.assertEqual(plan(s, cfg, meta=meta)["action"]["recipeId"], recipe_id)
            s["equipment"] = [{"defId": meta["recipes"][recipe_id]["output"]["defId"], "location": "bag"}]
            self.assertIsNone(plan(s, cfg, meta=meta)["action"])


class CraftWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = snapshot()
        self.account = {"id": "a", "automation_data": {"other": "preserved"}}
        self.client = AsyncMock(); self.client.command.side_effect = self.command
        self.logs = AsyncMock(); self.db = AsyncMock(return_value=[{}])
        for context in (patch.object(auto, "log", self.logs), patch.object(auto, "patch_rows", self.db)):
            context.start(); self.addCleanup(context.stop)

    async def command(self, name, payload, *, expected_version):
        self.assertEqual(name, "craft.start")
        self.assertEqual(expected_version, self.state["stateVersion"])
        recipe = auto.META["recipes"][payload["recipeId"]]
        self.state = copy.deepcopy(self.state); self.state["stateVersion"] += 1
        self.state["wallet"]["spirit_stone"] = str(int(self.state["wallet"]["spirit_stone"]) - recipe["stones"] * payload["count"])
        for item in recipe["inputs"]:
            self.state["materials"][item["itemId"]] -= item["qty"] * payload["count"]
        for _ in range(payload["count"]):
            self.state["crafting"]["jobs"].append({"id": f"job-{len(self.state['crafting']['jobs'])}", "recipeId": recipe["id"], "finishAt": NOW + recipe["durationMs"]})
        return {"state": self.state}

    async def test_mastery_only_one_profession_and_reasons_are_persisted(self):
        result = await auto._craft(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(len(result["crafting"]["jobs"]), 3)
        self.assertEqual(self.account["automation_data"]["other"], "preserved")
        self.assertEqual(self.account["automation_data"]["craftLevelFocus"]["profession"], "alchemy")
        self.assertEqual(len(self.account["automation_data"]["craftJobs"]), 3)
        self.assertEqual(self.db.await_count, 2)  # budget first, confirmed jobs + snapshot together
        self.assertIn("state_snapshot", self.db.await_args.args[2])

    async def test_blocked_craft_logs_settings_reason_and_next_action(self):
        self.state["materials"] = {}
        await auto._craft(self.client, self.state, settings(), self.account)
        self.client.command.assert_not_awaited()
        self.logs.assert_awaited_once()
        call = self.logs.await_args_list[0]
        self.assertEqual((call.args[1], call.args[2]), ("info", "craft.plan"))
        details = call.kwargs["details"]
        self.assertEqual(details["status"], "blocked")
        self.assertEqual(details["schema"], "craft_diagnostics_v1")
        self.assertTrue(details["settings"]["autoCraft"])
        self.assertTrue(details["settingLines"])
        self.assertTrue(details["resourceLines"])
        self.assertTrue(details["blocked"])
        self.assertIn("Xử lý chốt chặn", details["nextStep"])

    async def test_disabled_craft_does_not_plan_or_write_logs(self):
        await auto._craft(self.client, self.state, settings(autoCraft=False, autoMajorBreakthrough=False), self.account)
        self.client.command.assert_not_awaited()
        self.logs.assert_not_awaited()

    async def test_pending_major_breakthrough_stays_silent_and_sends_nothing(self):
        self.account["automation_data"]["majorBreakthroughPending"] = {"command": "craft.start"}
        await auto._craft(self.client, self.state, settings(autoMajorBreakthrough=True), self.account)
        self.client.command.assert_not_awaited()
        self.logs.assert_not_awaited()

    async def test_production_replans_materials_and_fills_distinct_recipes(self):
        self.state = max_all(self.state)
        self.state["character"] = {"level": 20, "realm": {"realmId": "ket_dan", "stage": 1}, "rateMilli": 2500}
        result = await auto._craft(self.client, self.state, settings(), self.account)
        ids = [job["recipeId"] for job in result["crafting"]["jobs"]]
        self.assertGreater(len(ids), 1)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(call.args[1]["count"] == 1 for call in self.client.command.await_args_list))

    async def test_production_yields_after_soft_quota_without_stopping_other_features(self):
        self.state = max_all(self.state)
        self.state["character"] = {"level": 20, "realm": {"realmId": "ket_dan", "stage": 1}, "rateMilli": 2500}
        budget = auto.TickBudget(feature_quota=1); token = auto._tick_budget.set(budget)
        try:
            await auto._craft(self.client, self.state, settings(), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertFalse(budget.stopped)

    async def test_budget_debited_before_paid_attempt_and_no_retry_after_timeout(self):
        self.state["professions"]["alchemy"] = {"level": 10, "crafted": 150, "next": None}
        async def timeout(*args, **kwargs):
            self.assertEqual(self.account["automation_data"]["craftLevelBudget"]["spent"], 45)
            raise TimeoutError("uncertain")
        self.client.command.side_effect = timeout
        budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
        try:
            await auto._craft(self.client, self.state, settings(), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertTrue(budget.stopped)
        self.assertIn("uncertain", budget.error)
        self.assertEqual(self.account["automation_data"]["craftLevelBudget"]["spent"], 45)

    async def test_failed_intent_or_budget_persistence_never_sends_command(self):
        self.state["professions"]["alchemy"] = {"level": 10, "crafted": 150, "next": None}
        self.db.side_effect = RuntimeError("db unavailable")
        await auto._craft(self.client, self.state, settings(), self.account)
        self.client.command.assert_not_awaited()

    async def test_empty_database_update_cannot_authorize_a_paid_attempt(self):
        self.state["professions"]["alchemy"] = {"level": 10, "crafted": 150, "next": None}
        self.db.return_value = []
        await auto._craft(self.client, self.state, settings(), self.account)
        self.client.command.assert_not_awaited()
        self.assertNotIn("craftLevelBudget", self.account["automation_data"])

    async def test_failed_intent_log_never_starts_a_batch(self):
        self.logs.side_effect = [RuntimeError("log unavailable"), None]
        await auto._craft(self.client, self.state, settings(), self.account)
        self.client.command.assert_not_awaited()

    async def test_response_missing_new_jobs_stops_after_one_attempt(self):
        self.client.command.side_effect = None
        self.client.command.return_value = {"state": {**self.state, "stateVersion": 11}}
        await auto._craft(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.logs.await_args.kwargs["details"]["status"], "uncertain")

    async def test_no_more_than_global_command_budget(self):
        self.state = max_all(self.state)
        budget = auto.TickBudget(attempts=11); token = auto._tick_budget.set(budget)
        try:
            await auto._craft(self.client, self.state, settings(), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(budget.attempts, 12)


class CraftConfigAndRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_defaults_are_subordinate_to_opt_in_parent_and_settings_validate(self):
        self.assertFalse(DEFAULT_CONFIG["autoCraft"])
        self.assertTrue(DEFAULT_CONFIG["craftMastery"])
        self.assertTrue(DEFAULT_CONFIG["craftProduce"])
        self.assertEqual(DEFAULT_CONFIG["craftLevelDaily"], 20)
        for change in ({"craftMastery": "true"}, {"craftProduce": 1}, {"craftLevelOrder": "wrong"},
                       {"craftBuild": "wrong"}, {"craftRecipeId": []}, {"craftRecipeId": "not-a-recipe"},
                       {"craftMatFloor": True}, {"craftLevelDaily": float("inf")}):
            with self.subTest(change=change), self.assertRaises(HTTPException):
                dashboard._config_for_update({}, change)

    async def test_cached_status_is_owner_scoped_and_read_only(self):
        row = {"id": "a", "state_snapshot": snapshot(), "automation_data": {}}
        with patch.object(dashboard, "owned_account", AsyncMock(return_value=row)) as owner, patch.object(dashboard, "account_config", AsyncMock(return_value=settings())), patch.object(dashboard, "GameClient") as game:
            result = await dashboard.crafting_status("a", False, {"id": "u"})
        owner.assert_awaited_once_with("u", "a")
        self.assertEqual(result["plan"]["action"]["recipeId"], "recipe_qi_pill")
        game.assert_not_called()

    async def test_refresh_uses_state_reader_not_mutation(self):
        with patch.object(dashboard, "owned_account", AsyncMock(return_value={"id": "a"})), patch.object(dashboard, "account_config", AsyncMock(return_value=settings())), patch.object(dashboard, "_account_state", AsyncMock(return_value=snapshot())) as reader:
            await dashboard.crafting_status("a", True, {"id": "u"})
        reader.assert_awaited_once()

    def test_crafting_status_requires_authentication(self):
        self.assertEqual(TestClient(app).get("/api/v1/accounts/a/crafting").status_code, 401)


if __name__ == "__main__":
    unittest.main()
