import copy
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.index import app
from api.routes.accounts import DEFAULT_CONFIG
from api.routes.dashboard import _config_for_update
from api.services import automation as auto
from api.services.game_client import GameAPIError
from api.services.game_rules import HUNT_TARGETS


NEW_FLAGS = (
    "autoEquipBest", "autoMinorTrial", "autoSectTasks", "autoSeasonTasks",
    "autoTitles", "autoPetAdopt", "autoNpcTalk", "autoNpcRewards", "autoHunt",
    "autoCleanup",
)


class ConfigTests(unittest.TestCase):
    def test_new_actions_default_off_for_existing_and_new_accounts(self):
        config = _config_for_update({}, {})
        for key in NEW_FLAGS:
            self.assertIs(DEFAULT_CONFIG[key], False)
            self.assertIs(config[key], False)

    def test_hunt_requires_reviewed_target(self):
        for change in ({"autoHunt": True}, {"huntPetId": "not-a-pet"}, {"huntPetId": []}):
            with self.subTest(change=change), self.assertRaises(HTTPException) as error:
                _config_for_update({}, change)
            self.assertEqual(error.exception.status_code, 422)
        config = _config_for_update({}, {"autoHunt": True, "huntPetId": "x2_pet_001"})
        self.assertTrue(config["autoHunt"])

    def test_no_truthy_strings_or_invalid_numeric_settings(self):
        for change in ({"autoHunt": "false"}, {"autoEquipBest": 1}, {"huntIntervalMin": "oops"},
                       {"huntReserveRuns": True}, {"huntReserveRuns": 1.5}, {"huntIntervalMin": float("inf")}):
            with self.subTest(change=change), self.assertRaises(HTTPException) as error:
                _config_for_update({}, change)
            self.assertEqual(error.exception.status_code, 422)

    def test_hunt_limits_are_clamped(self):
        config = _config_for_update({}, {"huntReserveRuns": 999, "huntIntervalMin": 0})
        self.assertEqual(config["huntReserveRuns"], 12)
        self.assertEqual(config["huntIntervalMin"], 1)

    def test_public_metadata_contains_all_reviewed_hunt_targets(self):
        response = TestClient(app).get("/api/v1/meta")
        self.assertEqual(response.status_code, 200)
        targets = response.json()["huntTargets"]
        self.assertEqual(targets, HUNT_TARGETS)
        self.assertEqual(len(targets), 40)
        self.assertEqual(targets["x2_pet_001"]["reqLevel"], 16)
        self.assertEqual(targets["x2_pet_033"]["reqLevel"], 62)
        self.assertEqual(targets["x2_pet_040"]["contractSeals"], 480)

    def test_dashboard_metadata_is_public_compact_and_has_no_private_state(self):
        response = TestClient(app).get("/api/v1/meta")
        data = response.json()
        self.assertEqual(data["stats"]["hp"]["label"], "Sinh lực")
        self.assertEqual(data["equipment"]["equip_t1_weapon"]["name"], "Thanh Khê Thiết Kiếm")
        self.assertEqual(set(data["equipment"]["equip_t1_weapon"]), {"id", "name", "slot", "rarity", "reqLevel"})
        self.assertIn("recipe_qi_pill", data["recipes"])
        self.assertNotIn("wallet", data)
        self.assertNotIn("session", str(data.keys()))
        self.assertLess(len(response.content), 500_000)


class AutomationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = {"id": "account-1", "enabled": True}
        self.state = {"stateVersion": 10}
        self.logs = AsyncMock()
        self.db = AsyncMock(return_value=[])
        self.log_patch = patch.object(auto, "log", self.logs)
        self.db_patch = patch.object(auto, "patch_rows", self.db)
        self.log_patch.start()
        self.db_patch.start()
        self.addCleanup(self.log_patch.stop)
        self.addCleanup(self.db_patch.stop)
        self.client = AsyncMock()
        self.client.command.side_effect = self.command

    async def command(self, name, payload, *, expected_version):
        self.assertEqual(expected_version, self.state["stateVersion"])
        self.state = copy.deepcopy(self.state)
        self.state["stateVersion"] += 1
        return {"state": self.state}

    def commands(self):
        return [(c.args[0], c.args[1]) for c in self.client.command.await_args_list]

    async def test_disabled_extensions_send_nothing(self):
        state = {"stateVersion": 10, "equipment": [{"location": "bag"}],
                 "pets": [{"id": "pet_cloud_fox", "owned": False, "canAdopt": True}],
                 "npcs": [{"id": "elder", "met": True, "talked": False, "affinity": 100, "claimed": []}]}
        for handler in (auto._equipment, auto._minor_trial, auto._extra_rewards, auto._pets, auto._npc):
            result = await handler(self.client, state, DEFAULT_CONFIG, self.account)
            self.assertIs(result, state)
        self.client.command.assert_not_awaited()

    async def test_ready_claims_require_explicit_complete_state_and_are_bounded(self):
        self.state.update({
            "sect": {"id": "sect_1"}, "sectExtra": {"tasks": [
                {"id": "ready", "claimed": False, "current": 2, "target": 2},
                {"id": "already", "claimed": True, "current": 2, "target": 2},
                {"id": "not-ready", "claimed": False, "current": 1, "target": 2},
                {"id": "missing", "claimed": False},
            ]},
            "season": {"tasks": [{"id": "festival", "claimed": False, "current": 1, "target": 1}]},
            "ascend": {"titles": [{"id": "title_1", "owned": False, "earned": True},
                                  {"id": "title_2", "owned": False, "earned": True}]},
        })
        result = await auto._extra_rewards(self.client, self.state,
                                          {"autoSectTasks": True, "autoSeasonTasks": True, "autoTitles": True}, self.account)
        self.assertEqual(self.commands(), [("sect.task.claim", {"taskId": "ready"}),
                                           ("season.task.claim", {"taskId": "festival"}),
                                           ("title.claim", {"titleId": "title_1"})])
        self.assertEqual(result["stateVersion"], 13)

    async def test_equip_delegates_to_game_without_selling_or_unlocking(self):
        await auto._equipment(self.client, self.state, {"autoEquipBest": True}, self.account)
        self.client.command.assert_not_awaited()
        self.state["equipment"] = [{"location": "equipped", "locked": True}, {"location": "bag"}]
        await auto._equipment(self.client, self.state, {"autoEquipBest": True}, self.account)
        self.assertEqual(self.commands(), [("equip.best", {})])

    async def test_minor_trial_only_for_unmet_trial_gate_and_sufficient_exp(self):
        self.state["character"] = {"next": "minor", "exp": "9007199254740993", "expNeed": "9007199254740994",
                                   "minorGate": {"kind": "trial", "have": 0, "need": 1}}
        await auto._minor_trial(self.client, self.state, {"autoMinorTrial": True}, self.account)
        self.client.command.assert_not_awaited()
        self.state["character"]["exp"] = self.state["character"]["expNeed"]
        await auto._minor_trial(self.client, self.state, {"autoMinorTrial": True}, self.account)
        self.assertEqual(self.commands(), [("minor.trial", {})])
        await auto._minor_trial(self.client, self.state, {"autoMinorTrial": True}, self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertIn("minorTrialLastAttemptAt", self.account["automation_data"])

    async def test_major_and_other_gate_types_are_never_attempted(self):
        for next_kind, gate in (("major", {"kind": "trial", "have": 0, "need": 1}),
                                ("minor", {"kind": "survey", "have": 0, "need": 1}),
                                ("minor", {"kind": "trial", "have": 1, "need": 1}),
                                ("minor", {"kind": "trial"})):
            self.state["character"] = {"next": next_kind, "exp": "100", "expNeed": "100", "minorGate": gate}
            await auto._minor_trial(self.client, self.state, {"autoMinorTrial": True}, self.account)
        self.client.command.assert_not_awaited()

    async def test_npc_talk_skips_locked_talked_and_max_affinity(self):
        self.state["npcs"] = [
            {"id": "locked", "met": False, "talked": False, "affinity": 0},
            {"id": "talked", "met": True, "talked": True, "affinity": 0},
            {"id": "max", "met": True, "talked": False, "affinity": 1000},
            *[{"id": f"ready{i}", "met": True, "talked": False, "affinity": 0} for i in range(3)],
        ]
        await auto._npc(self.client, self.state, {"autoNpcTalk": True}, self.account)
        self.assertEqual(self.commands(), [("npc.talk", {"npcId": "ready0"}), ("npc.talk", {"npcId": "ready1"})])

    async def test_npc_rewards_use_latest_state_after_talk(self):
        self.state["npcs"] = [{"id": "elder", "met": True, "talked": False, "affinity": 95, "claimed": []}]

        async def talk_and_claim(name, payload, *, expected_version):
            result = await self.command(name, payload, expected_version=expected_version)
            if name == "npc.talk":
                self.state["npcs"][0]["affinity"] = 103
                self.state["npcs"][0]["talked"] = True
            return result

        self.client.command.side_effect = talk_and_claim
        await auto._npc(self.client, self.state, {"autoNpcTalk": True, "autoNpcRewards": True}, self.account)
        self.assertEqual(self.commands(), [("npc.talk", {"npcId": "elder"}),
                                           ("npc.claim", {"npcId": "elder", "tierId": "acquainted"})])

    async def test_pet_adoption_is_bounded_and_does_not_equip_or_feed(self):
        self.state["pets"] = [{"id": "owned", "owned": True, "canAdopt": True},
                              {"id": "ready1", "owned": False, "canAdopt": True},
                              {"id": "ready2", "owned": False, "canAdopt": True}]
        await auto._pets(self.client, self.state, {"autoPetAdopt": True}, self.account)
        self.assertEqual(self.commands(), [("pet.adopt", {"petId": "ready1"})])

    def hunt_state(self):
        return {"stateVersion": 10, "character": {"level": 16},
                "pets": [{"id": "x2_pet_001", "owned": False, "canAdopt": False}],
                "x2": {"hunt": {"runs": 6, "seals": {}}}}

    async def test_hunt_requires_target_level_reserve_and_unowned_pet(self):
        config = {"autoHunt": True, "huntPetId": "x2_pet_001", "huntReserveRuns": 2}
        variants = []
        low = self.hunt_state(); low["character"]["level"] = 15; variants.append(low)
        reserve = self.hunt_state(); reserve["x2"]["hunt"]["runs"] = 2; variants.append(reserve)
        owned = self.hunt_state(); owned["pets"][0]["owned"] = True; variants.append(owned)
        ready = self.hunt_state(); ready["pets"][0]["canAdopt"] = True; variants.append(ready)
        enough = self.hunt_state(); enough["x2"]["hunt"]["seals"]["x2_pet_001"] = 20; variants.append(enough)
        for state in variants:
            await auto._pets(self.client, state, config, self.account)
        await auto._pets(self.client, self.hunt_state(), {"autoHunt": True}, self.account)
        self.client.command.assert_not_awaited()
        self.state = self.hunt_state()
        await auto._pets(self.client, self.state, config, self.account)
        self.assertEqual(self.commands(), [("hunt.run", {"petId": "x2_pet_001"})])
        await auto._pets(self.client, self.state, config, self.account)
        self.assertEqual(self.client.command.await_count, 1)

    async def test_attempt_history_preserves_other_keys_and_waits_even_after_loss(self):
        self.account["automation_data"] = {"bossLastFightAt": {"boss1": 123}, "minorTrialLastAttemptAt": 1}
        self.state = self.hunt_state()

        async def lose(name, payload, *, expected_version):
            result = await self.command(name, payload, expected_version=expected_version)
            result["result"] = {"win": False}
            return result

        self.client.command.side_effect = lose
        config = {"autoHunt": True, "huntPetId": "x2_pet_001"}
        await auto._pets(self.client, self.state, config, self.account)
        await auto._pets(self.client, self.state, config, self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.account["automation_data"]["bossLastFightAt"], {"boss1": 123})
        self.assertEqual(self.logs.await_args.args[1], "warning")

    async def test_global_budget_stops_at_twelve_and_preserves_state_version(self):
        budget = auto.TickBudget()
        token = auto._tick_budget.set(budget)
        try:
            for _ in range(20):
                self.state = await auto._best_effort(self.client, self.state, "equip.best", {}, self.account, "Equip")
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(budget.attempts, 12)
        self.assertEqual(self.client.command.await_count, 12)
        self.assertEqual(self.state["stateVersion"], 22)

    async def test_expired_budget_sends_nothing(self):
        token = auto._tick_budget.set(auto.TickBudget(deadline=time.monotonic() - 1))
        try:
            result = await auto._best_effort(self.client, self.state, "equip.best", {}, self.account, "Equip")
        finally:
            auto._tick_budget.reset(token)
        self.assertIs(result, self.state)
        self.client.command.assert_not_awaited()

    async def test_uncertain_failure_stops_all_later_commands_without_retry(self):
        failures = [TimeoutError(), GameAPIError("conflict", status_code=409, error_code="VERSION_CONFLICT")]
        for failure in failures:
            self.client.command.reset_mock()
            self.client.command.side_effect = failure
            budget = auto.TickBudget()
            token = auto._tick_budget.set(budget)
            try:
                for _ in range(3):
                    await auto._best_effort(self.client, self.state, "hunt.run", {}, self.account, "Hunt")
            finally:
                auto._tick_budget.reset(token)
            self.assertEqual(self.client.command.await_count, 1)
            self.assertTrue(budget.stopped)
            self.assertTrue(budget.error)

    async def test_missing_response_state_does_not_continue_with_stale_version(self):
        self.client.command.side_effect = None
        self.client.command.return_value = {"ok": True}
        budget = auto.TickBudget()
        token = auto._tick_budget.set(budget)
        try:
            await auto._best_effort(self.client, self.state, "equip.best", {}, self.account, "Equip")
            await auto._best_effort(self.client, self.state, "npc.talk", {}, self.account, "Talk")
        finally:
            auto._tick_budget.reset(token)
        self.assertTrue(budget.error)
        self.assertEqual(self.client.command.await_count, 1)

    async def test_tick_persists_failure_and_resets_its_context(self):
        self.client.get_state.return_value = self.state
        self.client.command.side_effect = TimeoutError("uncertain")
        with patch.object(auto, "GameClient", return_value=self.client), patch.object(auto, "decrypt_session", return_value="mock"):
            result = await auto.run_account_tick(self.account)
        self.assertFalse(result["completed"])
        self.assertIn("uncertain", result["error"])
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.db.await_args.args[2]["last_error"], result["error"])
        self.assertIsNone(auto._tick_budget.get())

    async def test_disabled_account_never_connects(self):
        with patch.object(auto, "GameClient") as client:
            result = await auto.run_account_tick({"id": "disabled", "enabled": False})
        self.assertTrue(result["skipped"])
        client.assert_not_called()

    async def test_successful_tick_uses_new_handlers_and_persists_latest_state(self):
        self.state.update({"character": {"autoMinor": True},
                           "equipment": [{"location": "bag"}],
                           "npcs": [{"id": "elder", "met": True, "talked": False, "affinity": 0}],
                           "settings": {"autoSalvageTier": 0, "autoSalvageMode": "salvage"}})
        self.account["config"] = {"autoEquipBest": True, "autoNpcTalk": True}
        self.client.get_state.return_value = self.state
        with patch.object(auto, "GameClient", return_value=self.client), patch.object(auto, "decrypt_session", return_value="mock"):
            result = await auto.run_account_tick(self.account)
        self.assertTrue(result["completed"])
        self.assertEqual(self.commands(), [("settle", {}), ("equip.best", {}), ("npc.talk", {"npcId": "elder"})])
        self.assertEqual(result["state"]["stateVersion"], 13)
        self.assertEqual(self.db.await_args.args[2]["state_snapshot"], result["state"])
        self.assertEqual(result["commandsAttempted"], 3)
        self.assertIsNone(auto._tick_budget.get())


if __name__ == "__main__":
    unittest.main()
