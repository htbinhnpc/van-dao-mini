import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.routes import dashboard
from api.routes.accounts import DEFAULT_CONFIG
from api.services import automation as auto
from api.services.breakthrough import (CHANCES, DEFINITIONS, INSURANCE, TOP_UP, natural, next_major,
                                       plan_breakthrough, validate_major_response, validate_trial_response)
from api.services.craft_profession import BREAKTHROUGH, PROFESSIONS, plan_crafting, priorities
from api.services.game_client import ALLOWED_COMMANDS
from api.services.cave import ROOMS, plan_cave_upgrade

NOW = 1794000000000


def snapshot(target="nguyen_anh", *, passed=False, fails=0):
    entry = next(d for d in DEFINITIONS if d["to"]["realmId"] == target)
    return {"stateVersion": 10, "character": {"realm": copy.deepcopy(entry["from"]), "next": "major",
            "level": 70, "exp": "100000000000000000000000001", "expNeed": "100000000000000000000000001"},
            "materials": {**{i["itemId"]: i["qty"] for i in entry["materials"]}, INSURANCE[0]: 1},
            "x2": {"btRoll": {"passed": entry["id"] if passed else None, "fails": {entry["id"]: fails}}, "ch01": {"branch": "a"}},
            "quests": [{"id": "q11_foundation_pill", "status": "claimed"}], "dao": {"mortalDone": True},
            "ascend": {"gates": [{"id": entry["gateId"], "passed": 5, "total": 5}] if entry["gateId"] else []},
            "counters": {}, "crafting": {"slots": 4, "jobs": [], "weekUsed": {}},
            "wallet": {"spirit_stone": "1000000000"}, "equipment": [], "bagCapacity": 100,
            "professions": {key: {"level": 1, "crafted": 0, "next": 3} for key in PROFESSIONS}}


def settings(**changes):
    return {**DEFAULT_CONFIG, "autoMajorBreakthrough": True, **changes}


def plan(state=None, config=None, data=None, **kwargs):
    return plan_breakthrough(state if state is not None else snapshot(), config or settings(), data, now_ms=NOW, meta=auto.META, **kwargs)


def response(before, command, payload=None, *, won=True):
    payload = payload or {}
    after = copy.deepcopy(before)
    after["stateVersion"] += 1
    entry = next_major(before)
    roll = after["x2"]["btRoll"]
    result = {"chance": CHANCES[min(roll["fails"].get(entry["id"], 0), 3)], "lost": []}
    if command == "quest.claim":
        next(q for q in after["quests"] if q["id"] == payload["questId"])["status"] = "claimed"
        return {"state": after}
    if command == "breakthrough.trial":
        after["counters"][f"trial:{entry['id']}"] = int(after["counters"].get(f"trial:{entry['id']}", 0)) + 1
        roll["passed"] = entry["id"] if won else None
        result["trialWon"] = won
    else:
        result["success"] = won
        if won:
            after["character"]["realm"] = copy.deepcopy(entry["to"])
            after["character"]["next"] = "minor"
        else:
            roll["fails"][entry["id"]] += 1
            roll["passed"] = None
        if payload.get("insurance"):
            after["materials"][payload["insurance"]] -= 1
            result["insurance"] = payload["insurance"]
        if payload.get("topUp"):
            after["materials"][TOP_UP[entry["to"]["realmId"]][0]] -= 1
    for item in entry["materials"]:
        cost = item["qty"] if command == "breakthrough.major" and won else item["qty"] // 5 if not won and item["lossOnFail"] else 0
        after["materials"][item["itemId"]] -= cost
        if cost:
            result["lost"].append({"itemId": item["itemId"], "qty": cost})
    return {"state": after, "result": result}


class MajorPlannerTests(unittest.TestCase):
    def test_exact_bigints_and_reject_invalid_numbers(self):
        for value in (True, False, -1, 1.5, float("inf"), "-1", "1e9", " 1", "١"):
            self.assertIsNone(natural(value), value)
        self.assertEqual(natural("10000000000000000000001"), 10000000000000000000001)

    def test_all_definitions_match_metadata_and_recipe_mapping(self):
        self.assertEqual(len(DEFINITIONS), 16)
        for entry in DEFINITIONS:
            with self.subTest(entry=entry["id"]):
                self.assertIn(entry["to"]["realmId"], auto.META["realms"])
                for item in entry["materials"]:
                    self.assertIn(item["itemId"], auto.META["items"])
                recipe = auto.META["recipes"][BREAKTHROUGH[entry["from"]["realmId"]]]
                self.assertEqual(recipe["output"]["itemId"], entry["materials"][0]["itemId"])
                self.assertEqual(plan(snapshot(entry["to"]["realmId"]))["action"]["command"],
                                 "breakthrough.trial" if entry["trialId"] else "breakthrough.major")

    def test_opt_in_and_pure_single_action(self):
        state = snapshot()
        before = copy.deepcopy(state)
        result = plan(state)
        self.assertEqual(result["action"]["command"], "breakthrough.trial")
        self.assertEqual(result["action"]["payload"], {})
        self.assertEqual(state, before)
        self.assertIsNone(plan(state, settings(autoMajorBreakthrough=False))["action"])

    def test_only_known_last_stage_and_major_next(self):
        for realm, kind in (({"realmId": "ket_dan", "stage": 3}, "minor"),
                            ({"realmId": "ket_dan", "stage": 4}, "minor"),
                            ({"realmId": "ket_dan", "stage": "4"}, "major"),
                            ("ket_dan", "major"), ({"realmId": "unknown", "stage": 4}, "major")):
            state = snapshot(); state["character"].update(realm=realm, next=kind)
            self.assertIsNone(plan(state)["action"])

    def test_required_quest_claim_before_trial_and_no_skipping_active_quest(self):
        state = snapshot("truc_co")
        state["quests"][0]["status"] = "claimable"
        self.assertEqual(plan(state)["action"]["payload"], {"questId": "q11_foundation_pill"})
        state["quests"][0]["status"] = "active"
        self.assertEqual(plan(state)["phase"], "quest")
        state["quests"] = [{"id": "q10_tower", "status": "claimable"}]
        # Use a known predecessor id, not a guessed quest id.
        state["quests"][0]["id"] = next(q["id"] for q in auto.META["quests"].values() if q.get("order") == 10)
        self.assertEqual(plan(state)["action"]["command"], "quest.claim")
        state["quests"] = []
        self.assertIsNone(plan(state)["action"])

    def test_branch_mortal_and_gate_are_explicit_not_invented(self):
        state = snapshot(); state["x2"]["ch01"] = {"branch": None}
        self.assertEqual(plan(state)["phase"], "quest")
        state = snapshot("hoa_than"); state["dao"] = {}
        self.assertEqual(plan(state)["phase"], "quest")
        for target in ("khong_niet", "khong_kiep"):
            state = snapshot(target)
            self.assertEqual(plan(state)["action"]["command"], "breakthrough.major")
            for gates in ([], [{"id": next_major(state)["gateId"], "passed": 4, "total": 5}],
                          [{"id": next_major(state)["gateId"], "passed": 0, "total": 0}]):
                state["ascend"]["gates"] = gates
                self.assertEqual(plan(state)["phase"], "gate")

    def test_missing_resources_experience_and_roll_never_authorize_spend(self):
        changes = [lambda s: s.pop("materials"), lambda s: s["materials"].pop("item_nascent_pill"),
                   lambda s: s["character"].pop("expNeed"), lambda s: s["character"].__setitem__("expNeed", "0"),
                   lambda s: s["x2"].pop("btRoll"), lambda s: s["x2"]["btRoll"].pop("passed"),
                   lambda s: s["x2"]["btRoll"].__setitem__("fails", None)]
        for change in changes:
            state = snapshot(); change(state)
            self.assertIsNone(plan(state)["action"])
        state = snapshot(); state["character"]["exp"] = str(int(state["character"]["expNeed"]) - 1)
        self.assertEqual(plan(state)["phase"], "experience")
        for version in (None, True, 0, "10"):
            state = snapshot(); state["stateVersion"] = version
            self.assertIsNone(plan(state)["action"])
            self.assertIsNone(plan_crafting(state, settings(), auto.META, now_ms=NOW)["action"])

    def test_malformed_nested_state_does_not_crash_or_send(self):
        for key in ("x2", "dao", "ascend", "counters", "materials", "character"):
            state = snapshot(); state[key] = ["unexpected"]
            self.assertIsNone(plan(state)["action"])
        state = snapshot(); state["x2"]["ch01"] = ["unexpected"]
        self.assertIsNone(plan(state)["action"])

    def test_chances_minimum_does_not_force_failures(self):
        for fails, chance in enumerate(CHANCES):
            self.assertEqual(plan(snapshot(fails=fails))["chance"], chance)
        self.assertIsNone(plan(snapshot(fails=0), settings(majorMinChance=40))["action"])
        self.assertIsNotNone(plan(snapshot(fails=1), settings(majorMinChance=40))["action"])
        state = snapshot(); state["x2"]["btRoll"]["fails"] = {}
        self.assertEqual(plan(state)["chance"], 30)  # Client defines absent per-id key as zero.

    def test_insurance_is_required_only_for_lossy_major_roll_not_trial(self):
        state = snapshot(passed=True)
        self.assertEqual(plan(state)["action"]["payload"], {"insurance": INSURANCE[0]})
        del state["materials"][INSURANCE[0]]
        self.assertEqual(plan(state)["phase"], "insurance")
        self.assertEqual(plan(state, settings(majorUseInsurance=False))["action"]["payload"], {})
        state["x2"]["btRoll"]["passed"] = None
        self.assertEqual(plan(state)["action"]["command"], "breakthrough.trial")
        self.assertEqual(plan(snapshot(passed=True, fails=3))["action"]["payload"], {})
        self.assertEqual(plan(snapshot("ket_dan", passed=True))["action"]["payload"], {})
        for item in INSURANCE:
            state = snapshot(passed=True); state["materials"] = {k: v for k, v in state["materials"].items() if k not in INSURANCE}
            state["materials"][item] = 1
            self.assertEqual(plan(state)["action"]["payload"]["insurance"], item)

    def test_topup_exact_thresholds_owned_only_and_never_sent_to_trial(self):
        for target, (item, pct) in TOP_UP.items():
            state = snapshot(target, passed=True)
            state["character"].update(exp=str(pct), expNeed="100")
            state["materials"][item] = 1
            self.assertIsNone(plan(state)["action"])
            self.assertTrue(plan(state, settings(majorAllowTopUp=True))["action"]["payload"]["topUp"])
            state["character"]["exp"] = str(pct - 1)
            self.assertIsNone(plan(state, settings(majorAllowTopUp=True))["action"])
        state = snapshot(passed=False); state["character"].update(exp="85", expNeed="100"); state["materials"]["x2_pill_11"] = 1
        self.assertEqual(plan(state, settings(majorAllowTopUp=True))["action"]["payload"], {})

    def test_persistent_uncertain_lock_and_rate_limit(self):
        self.assertEqual(plan(data={"majorBreakthroughPending": {"command": "breakthrough.major"}})["phase"], "uncertain")
        self.assertEqual(plan(data={"majorBreakthroughLastAttemptAt": NOW - 29 * 60000})["phase"], "cooldown")
        self.assertIsNotNone(plan(data={"majorBreakthroughLastAttemptAt": NOW - 30 * 60000})["action"])

    def test_defaults_config_types_clamps_and_allowlist(self):
        self.assertFalse(DEFAULT_CONFIG["autoMajorBreakthrough"])
        for change in ({"autoMajorBreakthrough": "true"}, {"majorUseInsurance": 1}, {"majorAllowTopUp": "false"}, {"majorMinChance": True}, {"majorRetryMinutes": 1.5}):
            with self.assertRaises(HTTPException):
                dashboard._config_for_update({}, change)
        result = dashboard._config_for_update({}, {"majorMinChance": 200, "majorRetryMinutes": 1})
        self.assertEqual((result["majorMinChance"], result["majorRetryMinutes"]), (100, 10))
        self.assertTrue({"breakthrough.trial", "breakthrough.major"}.issubset(ALLOWED_COMMANDS))


class MajorResponseTests(unittest.TestCase):
    def test_trial_win_and_loss_require_matching_state(self):
        before = snapshot()
        for won in (True, False):
            reply = response(before, "breakthrough.trial", won=won)
            validate_trial_response(before, reply["state"], reply["result"])
            reply["state"]["counters"] = {}
            with self.assertRaises(ValueError):
                validate_trial_response(before, reply["state"], reply["result"])

    def test_trial_does_not_increment_major_failure_counter(self):
        before = snapshot()
        reply = response(before, "breakthrough.trial", won=False)
        reply["state"]["x2"]["btRoll"]["fails"]["bt_nguyen_anh"] = 1
        with self.assertRaises(ValueError):
            validate_trial_response(before, reply["state"], reply["result"])

    def test_major_success_failure_insurance_and_topup(self):
        before = snapshot(passed=True)
        before["materials"]["x2_pill_11"] = 1
        payload = {"insurance": INSURANCE[0], "topUp": True}
        for won in (True, False):
            reply = response(before, "breakthrough.major", payload, won=won)
            validate_major_response(before, reply["state"], reply["result"], payload)
            for change in (lambda s: s.__setitem__("stateVersion", 10),
                           lambda s: s["materials"].__setitem__(INSURANCE[0], 1),
                           lambda s: s["materials"].__setitem__("x2_pill_11", 1),
                           lambda s: s["materials"].__setitem__("item_nascent_pill", 10)):
                changed = copy.deepcopy(reply["state"]); change(changed)
                with self.assertRaises(ValueError):
                    validate_major_response(before, changed, reply["result"], payload)

    def test_no_false_success_or_unconfirmed_failure(self):
        before = snapshot(passed=True)
        for outcome in ({}, {"success": "true"}, {"success": True}, {"success": False}):
            with self.assertRaises(ValueError):
                validate_major_response(before, {**before, "stateVersion": 11}, outcome, {})


class MajorPreparationTests(unittest.TestCase):
    def craft(self, state, **changes):
        return plan_crafting(state, settings(**changes), auto.META, now_ms=NOW)

    def supply(self, state, recipe_id):
        for item in auto.META["recipes"][recipe_id]["inputs"]:
            state["materials"][item["itemId"]] = 1000

    def test_narrow_preparation_works_without_enabling_general_crafting(self):
        state = snapshot("truc_co"); del state["materials"]["item_foundation_pill"]
        self.supply(state, "recipe_foundation_pill")
        self.assertEqual(self.craft(state)["action"]["recipeId"], "recipe_foundation_pill")
        state["crafting"]["jobs"] = [{"id": "job", "recipeId": "recipe_foundation_pill"}]
        self.assertIsNone(self.craft(state)["action"])
        state = snapshot()
        self.supply(state, "recipe_qi_pill")
        self.assertIsNone(self.craft(state)["action"])  # Never mastery/filler.

    def test_insurance_preparation_is_one_interchangeable_aid_including_pending(self):
        state = snapshot(); del state["materials"][INSURANCE[0]]
        self.supply(state, "recipe_aid_recovery_pill")
        action = self.craft(state)["action"]
        self.assertEqual(action["recipeId"], "recipe_aid_recovery_pill")
        state["crafting"]["jobs"] = [{"id": "aid", "recipeId": action["recipeId"]}]
        self.assertIsNone(self.craft(state)["action"])
        state["crafting"]["jobs"] = []
        state["materials"][INSURANCE[2]] = 1
        self.assertIsNone(self.craft(state)["action"])
        del state["materials"][INSURANCE[2]]
        self.assertIsNone(self.craft(state, majorUseInsurance=False)["action"])

    def test_topup_recipe_is_only_prepared_when_allowed_and_near_threshold(self):
        state = snapshot(); state["character"].update(exp="85", expNeed="100")
        self.supply(state, "x2_recipe_011")
        self.assertIsNone(self.craft(state)["action"])
        self.assertEqual(self.craft(state, majorAllowTopUp=True)["action"]["recipeId"], "x2_recipe_011")
        state["character"]["exp"] = "84"
        self.assertIsNone(self.craft(state, majorAllowTopUp=True)["action"])

    def test_breakthrough_materials_stone_reserve_and_pending_lock_are_protected(self):
        state = snapshot("ket_dan"); del state["materials"]["item_core_pill"]
        recipe = auto.META["recipes"]["recipe_core_pill"]
        self.supply(state, recipe["id"])
        state["wallet"]["spirit_stone"] = str(recipe["stones"] + 999)
        self.assertIsNone(self.craft(state)["action"])
        state["wallet"]["spirit_stone"] = "1000000000"
        for item in recipe["inputs"]:
            if item["itemId"] == "item_frost_crystal":
                state["materials"][item["itemId"]] = item["qty"] + 19
                self.assertIsNone(self.craft(state)["action"])
        blocked = plan_crafting(state, settings(), auto.META, {"majorBreakthroughPending": {"command": "craft.start"}}, now_ms=NOW)
        self.assertIsNone(blocked["action"])

    def test_cave_keeps_direct_breakthrough_materials_with_general_craft_off(self):
        state = snapshot("ket_dan")
        state["cave"] = {"unlocked": True, "rooms": [
            {"id": key, "level": 0 if key == "tu_linh" else room["maxLevel"], "upgradeFinishAt": None}
            for key, room in ROOMS.items()]}
        config = settings(autoCaveUpgrade=True, caveReserveStones=0, caveMatFloor=0, craftReserveStones=0, craftMatFloor=0)
        self.assertIsNone(plan_cave_upgrade(state, config, auto.META, now_ms=NOW)["action"])
        state["materials"]["item_frost_crystal"] += 4
        self.assertEqual(plan_cave_upgrade(state, config, auto.META, now_ms=NOW)["action"]["roomId"], "tu_linh")


class MajorWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = snapshot()
        self.account = {"id": "a", "automation_data": {"other": "preserved"}}
        self.client = AsyncMock()
        self.client.command.side_effect = self.command
        self.logs, self.db = AsyncMock(), AsyncMock(return_value=[{}])
        for context in (patch.object(auto, "log", self.logs), patch.object(auto, "patch_rows", self.db), patch.object(auto.time, "time", return_value=NOW / 1000)):
            context.start(); self.addCleanup(context.stop)

    async def command(self, name, payload, *, expected_version):
        self.assertEqual(expected_version, self.state["stateVersion"])
        self.assertIsNotNone(self.account["automation_data"]["majorBreakthroughPending"])
        reply = response(self.state, name, payload)
        self.state = reply["state"]
        return reply

    async def run_major(self, config=None):
        return await auto._major_breakthrough(self.client, self.state, config or settings(), self.account)

    async def test_trial_then_major_are_separate_ticks_with_cooldown(self):
        state = await self.run_major()
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(state["x2"]["btRoll"]["passed"], "bt_nguyen_anh")
        self.assertIsNone(self.account["automation_data"]["majorBreakthroughPending"])
        await self.run_major()
        self.assertEqual(self.client.command.await_count, 1)
        self.account["automation_data"]["majorBreakthroughLastAttemptAt"] -= 30 * 60000
        state = await self.run_major()
        self.assertEqual(self.client.command.await_count, 2)
        self.assertEqual(state["character"]["realm"], {"realmId": "nguyen_anh", "stage": 1})
        self.assertEqual(self.account["automation_data"]["other"], "preserved")
        self.assertEqual(self.db.await_args.args[2]["state_snapshot"], state)

    async def test_quest_is_claimed_even_when_general_claim_toggle_is_off(self):
        self.state = snapshot("truc_co"); self.state["quests"][0]["status"] = "claimable"
        await self.run_major(settings(autoQuests=False))
        self.assertEqual(self.client.command.await_args.args, ("quest.claim", {"questId": "q11_foundation_pill"}))

    async def test_confirmed_failure_is_logged_and_replanned_after_rest_not_looped(self):
        async def lose(name, payload, **kwargs):
            reply = response(self.state, name, payload, won=False)
            self.state = reply["state"]
            return reply
        self.client.command.side_effect = lose
        state = await self.run_major()
        self.assertEqual(state["materials"]["item_ember_sand"], 24)
        self.assertIsNone(self.account["automation_data"]["majorBreakthroughPending"])
        self.assertEqual(self.logs.await_args.args[1], "warning")
        await self.run_major()
        self.assertEqual(self.client.command.await_count, 1)

    async def test_timeout_persists_lock_across_ticks_and_stops_all_mutations(self):
        self.client.command.side_effect = TimeoutError("uncertain")
        budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
        try:
            await self.run_major()
            await auto._minor_trial(self.client, self.state, settings(autoMinorTrial=True), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertTrue(budget.stopped)
        self.assertIn("uncertain", budget.error)
        self.assertEqual(self.client.command.await_count, 1)
        self.account["automation_data"]["majorBreakthroughLastAttemptAt"] = 0
        await self.run_major()
        await auto._craft(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)

    async def test_unconfirmed_state_is_kept_without_success_or_retry(self):
        new_state = copy.deepcopy(self.state); new_state["stateVersion"] += 1
        self.client.command.side_effect = None
        self.client.command.return_value = {"state": new_state, "result": {"trialWon": True}}
        budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
        try:
            result = await self.run_major()
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(result, new_state)
        self.assertTrue(budget.stopped)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertFalse(any(call.args[1] == "success" for call in self.logs.await_args_list))
        self.assertIsNotNone(self.account["automation_data"]["majorBreakthroughPending"])

    async def test_no_command_when_lock_cannot_be_saved_disabled_or_minor_only(self):
        await self.run_major(settings(autoMajorBreakthrough=False))
        await auto._minor_trial(self.client, self.state, settings(autoMinorTrial=True), self.account)
        self.client.command.assert_not_awaited()
        self.db.return_value = []
        await self.run_major()
        self.client.command.assert_not_awaited()

    async def test_narrow_craft_worker_persists_lock_and_never_starts_mastery(self):
        self.state = snapshot("truc_co"); del self.state["materials"]["item_foundation_pill"]
        recipe = auto.META["recipes"]["recipe_foundation_pill"]
        for item in recipe["inputs"]:
            self.state["materials"][item["itemId"]] = 100
        async def craft(name, payload, *, expected_version):
            self.assertEqual(name, "craft.start")
            self.assertEqual(payload, {"recipeId": recipe["id"], "count": 1})
            self.assertIsNotNone(self.account["automation_data"]["majorBreakthroughPending"])
            self.state = copy.deepcopy(self.state); self.state["stateVersion"] += 1
            self.state["crafting"]["jobs"].append({"id": "job1", "recipeId": recipe["id"]})
            return {"state": self.state}
        self.client.command.side_effect = craft
        result = await auto._craft(self.client, self.state, settings(), self.account)
        self.assertEqual(len(result["crafting"]["jobs"]), 1)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertIsNone(self.account["automation_data"]["majorBreakthroughPending"])

    async def test_narrow_craft_timeout_is_locked_across_ticks(self):
        self.state = snapshot(); del self.state["materials"][INSURANCE[0]]
        self.state["materials"]["item_spirit_herb"] = 100
        self.client.command.side_effect = TimeoutError("uncertain")
        budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
        try:
            await auto._craft(self.client, self.state, settings(), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertTrue(budget.stopped)
        await auto._craft(self.client, self.state, settings(), self.account)
        await self.run_major()
        self.assertEqual(self.client.command.await_count, 1)


class MajorRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_arbitrary_command_endpoint_cannot_bypass_major_guards(self):
        for command in ("breakthrough.trial", "breakthrough.major"):
            with patch.object(dashboard, "owned_account", AsyncMock()) as owned:
                with self.assertRaises(HTTPException) as raised:
                    await dashboard.send_command("a", dashboard.CommandRequest(command=command), {"id": "u"})
                self.assertEqual(raised.exception.status_code, 400)
                owned.assert_not_awaited()

    async def test_only_explicit_off_save_acknowledges_lock_after_config_is_stored(self):
        account = {"id": "a", "automation_data": {"other": 1, "majorBreakthroughPending": {"command": "breakthrough.major"}}}
        for update, expected_clear in (({"autoMajorBreakthrough": False}, True), ({"autoMajorBreakthrough": True}, False), ({"autoDaily": False}, False)):
            db = AsyncMock(return_value=[{}])
            with (patch.object(dashboard, "owned_account", AsyncMock(return_value=account)),
                  patch.object(dashboard, "account_config", AsyncMock(return_value=settings())),
                  patch.object(dashboard, "patch_rows", db), patch.object(dashboard, "insert_one", AsyncMock())):
                await dashboard.save_config("a", dashboard.ConfigUpdate(config=update), {"id": "u"})
            clears = [call for call in db.await_args_list if "automation_data" in call.args[2]]
            self.assertEqual(bool(clears), expected_clear)
            if expected_clear:
                self.assertEqual(db.await_args_list[0].args[0], "account_configs")
                self.assertEqual(clears[0].args[2]["automation_data"], {"other": 1})
                self.assertIn("automation_data=eq.", clears[0].args[1])
                self.assertIn("lease_until.is.null", clears[0].args[1])

    async def test_failed_off_save_never_acknowledges_uncertain_attempt(self):
        account = {"id": "a", "automation_data": {"majorBreakthroughPending": {"command": "breakthrough.major"}}}
        db = AsyncMock(return_value=[])
        with (patch.object(dashboard, "owned_account", AsyncMock(return_value=account)),
              patch.object(dashboard, "account_config", AsyncMock(return_value=settings())),
              patch.object(dashboard, "patch_rows", db)):
            with self.assertRaises(HTTPException):
                await dashboard.save_config("a", dashboard.ConfigUpdate(config={"autoMajorBreakthrough": False}), {"id": "u"})
        self.assertFalse(any("automation_data" in call.args[2] for call in db.await_args_list))

    async def test_major_manual_tick_requires_lease_and_uses_fresh_automation_data(self):
        stale = {"id": "a", "automation_data": {}}
        fresh = {"id": "a", "automation_data": {"majorBreakthroughPending": {"command": "breakthrough.major"}}}
        for available in (True, False):
            db = AsyncMock(return_value=[fresh] if available else [])
            run = AsyncMock(return_value={"completed": True})
            with (patch.object(dashboard, "owned_account", AsyncMock(return_value=stale)),
                  patch.object(dashboard, "account_config", AsyncMock(return_value=settings())),
                  patch.object(dashboard, "patch_rows", db), patch.object(dashboard, "run_account_tick", run)):
                if available:
                    await dashboard.manual_tick("a", {"id": "u"})
                    self.assertEqual(run.await_args.args[0]["automation_data"], fresh["automation_data"])
                    self.assertEqual(db.await_args.args[2], {"lease_until": None})
                    self.assertIn("lease_until=eq.", db.await_args.args[1])
                else:
                    with self.assertRaises(HTTPException) as raised:
                        await dashboard.manual_tick("a", {"id": "u"})
                    self.assertEqual(raised.exception.status_code, 409)
                    run.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
