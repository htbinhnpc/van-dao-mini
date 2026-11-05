import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.index import app
from api.routes import dashboard
from api.routes.accounts import DEFAULT_CONFIG
from api.services import automation as auto
from api.services.cave import (CRAFT_ORDER, ROOM_ORDER, plan_cave_upgrade, upgrade_cost,
                               validate_upgrade_response)
from api.services.craft_profession import PROFESSIONS
from api.services.game_client import ALLOWED_COMMANDS


NOW = 1793836800000


def snapshot():
    return {
        "stateVersion": 30, "serverNow": NOW,
        "wallet": {"spirit_stone": "1000000"},
        "materials": {key: 10000 for key in
                      ("item_spirit_herb", "item_iron_ore", "item_beast_hide", "item_frost_crystal")},
        "cave": {"unlocked": True, "plots": 0, "fields": [],
                 "rooms": [{"id": room_id, "level": 0, "upgradeFinishAt": None}
                           for room_id in ROOM_ORDER]},
        "quests": [], "crafting": {"slots": 4, "jobs": [], "weekUsed": {}},
        "professions": {key: {"level": 1, "crafted": 0, "next": 3} for key in PROFESSIONS},
        "character": {"level": 16, "realm": "unknown"},
    }


def settings(**changes):
    return {**DEFAULT_CONFIG, "autoCaveUpgrade": True, "craftQiTarget": 0, "craftCharmTarget": 0, **changes}


def plan(state=None, config=None, meta=None):
    return plan_cave_upgrade(state or snapshot(), config or settings(), meta or auto.META, now_ms=NOW)


class CavePlannerTests(unittest.TestCase):
    def test_upgrade_cost_matches_public_client_formula(self):
        self.assertEqual(upgrade_cost("tu_linh", 0), {
            "stones": 300, "items": [{"itemId": "item_frost_crystal", "qty": 4}], "durationMs": 600000})
        cost = upgrade_cost("dan_phong", 2)
        self.assertEqual(cost["stones"], round(500 * 1.7 ** 2))
        self.assertEqual(cost["items"], [{"itemId": "item_spirit_herb", "qty": 60}])
        self.assertEqual(cost["durationMs"], 45 * 60000)
        self.assertIsNone(upgrade_cost("tu_linh", 10))
        self.assertIsNone(upgrade_cost("unknown", 0))

    def test_craft_order_is_default_and_planner_does_not_mutate_state(self):
        s = snapshot(); before = copy.deepcopy(s)
        result = plan(s)
        self.assertEqual(CRAFT_ORDER[0], "dan_phong")
        self.assertEqual(result["action"]["roomId"], "dan_phong")
        self.assertEqual((result["action"]["level"], result["action"]["targetLevel"], result["action"]["stones"]), (0, 1, 500))
        self.assertEqual(s, before)

    def test_cultivation_and_balanced_orders(self):
        self.assertEqual(plan(config=settings(caveRoomOrder="cultivation"))["action"]["roomId"], "tu_linh")
        s = snapshot()
        # Balanced compares level/maxLevel, so a low-level small room can lead.
        s["cave"]["rooms"][0]["level"] = 4
        s["cave"]["rooms"][1]["level"] = 5
        self.assertEqual(plan(s, settings(caveRoomOrder="balanced"))["action"]["roomId"], "dan_phong")

    def test_active_cave_quest_overrides_configured_order(self):
        s = snapshot(); s["quests"] = [{"id": "q14_cave", "status": "active", "current": 0, "target": 1}]
        result = plan(s)
        self.assertEqual(result["action"]["roomId"], "tu_linh")
        self.assertEqual(result["action"]["reason"], "Nhiệm vụ động phủ đang làm")
        s["cave"]["rooms"][0]["level"] = 1  # objective already met → normal order
        self.assertEqual(plan(s)["action"]["roomId"], "dan_phong")

    def test_blocked_quest_room_waits_instead_of_spending_elsewhere(self):
        s = snapshot(); s["quests"] = [{"id": "q14_cave", "status": "active", "current": 0, "target": 1}]
        s["materials"]["item_frost_crystal"] = 20  # floor 20 + cost 4
        result = plan(s)
        self.assertIsNone(result["action"])
        self.assertIn("nhiệm vụ", result["reason"])
        self.assertEqual(result["blocked"][0]["name"], "Tụ Linh Trận")

    def test_active_room_blocks_every_other_upgrade(self):
        s = snapshot(); s["cave"]["rooms"][3]["upgradeFinishAt"] = NOW + 60000
        result = plan(s)
        self.assertIsNone(result["action"])
        self.assertEqual(result["active"]["id"], "khi_phong")

    def test_missing_or_invalid_cave_state_is_not_guessed(self):
        cases = [
            None,
            {"unlocked": False, "rooms": []},
            {"unlocked": True, "rooms": snapshot()["cave"]["rooms"][:-1]},
            {**snapshot()["cave"], "rooms": [{**room, "level": True} if room["id"] == "kho" else room
                                             for room in snapshot()["cave"]["rooms"]]},
            {**snapshot()["cave"], "rooms": [{**room, "upgradeFinishAt": 0} if room["id"] == "kho" else room
                                             for room in snapshot()["cave"]["rooms"]]},
            {**snapshot()["cave"], "rooms": snapshot()["cave"]["rooms"] + [{"id": "extra", "level": 0, "upgradeFinishAt": None}]},
        ]
        for cave in cases:
            s = snapshot()
            if cave is None:
                s.pop("cave")
            else:
                s["cave"] = cave
            result = plan(s)
            self.assertEqual(result["phase"], "unknown")
            self.assertIsNone(result["action"])

    def test_cave_reserve_and_autocraft_reserve_protect_stones(self):
        s = snapshot(); s["wallet"]["spirit_stone"] = "1600"
        self.assertEqual(plan(s, settings(autoCraft=False))["action"]["roomId"], "dan_phong")
        self.assertIsNone(plan(s, settings(autoCraft=True))["action"])

    def test_autocraft_quest_materials_are_not_spent_on_cave(self):
        s = snapshot(); s["quests"] = [{"id": "q05_first_craft", "status": "active", "current": 0, "target": 1}]
        s["materials"]["item_spirit_herb"] = 43  # floor 20 + cave 20 + craft 4 - 1
        self.assertNotEqual(plan(s, settings(autoCraft=True))["action"]["roomId"], "dan_phong")
        s["materials"]["item_spirit_herb"] = 44
        self.assertEqual(plan(s, settings(autoCraft=True))["action"]["roomId"], "dan_phong")

    def test_response_validation_rejects_uncertain_or_wrong_upgrade(self):
        before = snapshot()
        after = copy.deepcopy(before)
        after["stateVersion"] += 1
        room = next(room for room in after["cave"]["rooms"] if room["id"] == "dan_phong")
        room["level"] = 1
        room["upgradeFinishAt"] = NOW + 900000
        validate_upgrade_response(before, after, "dan_phong")

        mutations = [
            lambda value: value.__setitem__("stateVersion", before["stateVersion"]),
            lambda value: next(room for room in value["cave"]["rooms"] if room["id"] == "dan_phong").__setitem__("level", 3),
            lambda value: next(room for room in value["cave"]["rooms"] if room["id"] == "dan_phong").__setitem__("upgradeFinishAt", None),
            lambda value: next(room for room in value["cave"]["rooms"] if room["id"] == "kho").__setitem__("level", 1),
            lambda value: next(room for room in value["cave"]["rooms"] if room["id"] == "kho").__setitem__("upgradeFinishAt", NOW + 1),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(after)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                validate_upgrade_response(before, changed, "dan_phong")

    def test_config_defaults_validation_and_public_metadata(self):
        self.assertFalse(DEFAULT_CONFIG["autoCaveUpgrade"])
        self.assertEqual(DEFAULT_CONFIG["caveRoomOrder"], "craft")
        for change in ({"autoCaveUpgrade": "true"}, {"autoCaveUpgrade": 1},
                       {"caveRoomOrder": "wrong"}, {"caveReserveStones": True},
                       {"caveMatFloor": True}, {"caveReserveStones": float("inf")}):
            with self.subTest(change=change), self.assertRaises(HTTPException):
                dashboard._config_for_update({}, change)
        config = dashboard._config_for_update({}, {"autoCaveUpgrade": True, "caveReserveStones": 10 ** 30, "caveMatFloor": 5})
        self.assertTrue(config["autoCaveUpgrade"])
        self.assertEqual(config["caveMatFloor"], 5)
        self.assertGreater(config["caveReserveStones"], 0)

        response = TestClient(app).get("/api/v1/meta")
        self.assertEqual(response.status_code, 200)
        rooms = response.json()["rooms"]
        self.assertEqual([room["id"] for room in rooms], list(ROOM_ORDER))
        self.assertEqual(rooms[0]["maxLevel"], 10)

    def test_cave_upgrade_is_allowlisted_but_rush_is_not(self):
        self.assertIn("cave.upgrade", ALLOWED_COMMANDS)
        self.assertNotIn("cave.rush", ALLOWED_COMMANDS)


class CaveWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = snapshot()
        self.account = {"id": "a", "automation_data": {"other": "preserved"}}
        self.client = AsyncMock(); self.client.command.side_effect = self.command
        self.logs = AsyncMock(); self.db = AsyncMock(return_value=[{}])
        for context in (patch.object(auto, "log", self.logs), patch.object(auto, "patch_rows", self.db)):
            context.start(); self.addCleanup(context.stop)

    async def command(self, name, payload, *, expected_version):
        self.assertEqual(name, "cave.upgrade")
        self.assertEqual(expected_version, self.state["stateVersion"])
        next_state = copy.deepcopy(self.state)
        next_state["stateVersion"] += 1
        room = next(room for room in next_state["cave"]["rooms"] if room["id"] == payload["roomId"])
        cost = upgrade_cost(room["id"], room["level"])
        next_state["wallet"]["spirit_stone"] = str(int(next_state["wallet"]["spirit_stone"]) - cost["stones"])
        for item in cost["items"]:
            next_state["materials"][item["itemId"]] -= item["qty"]
        room["level"] += 1
        room["upgradeFinishAt"] = NOW + cost["durationMs"]
        self.state = next_state
        return {"state": next_state}

    async def test_worker_sends_exactly_one_confirmed_upgrade(self):
        result = await auto._cave(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.client.command.await_args.args[1], {"roomId": "dan_phong"})
        dan_phong = next(room for room in result["cave"]["rooms"] if room["id"] == "dan_phong")
        self.assertEqual(dan_phong["level"], 1)
        self.assertEqual(self.logs.await_args.kwargs["details"]["status"], "succeeded")
        self.assertEqual(self.account["automation_data"]["other"], "preserved")

    async def test_active_room_or_disabled_auto_sends_nothing(self):
        active = snapshot(); active["cave"]["rooms"][0]["upgradeFinishAt"] = NOW + 1
        await auto._cave(self.client, active, settings(), self.account)
        self.client.command.assert_not_awaited()
        await auto._cave(self.client, self.state, settings(autoCaveUpgrade=False), self.account)
        self.client.command.assert_not_awaited()

    async def test_timeout_stops_the_tick_without_retry(self):
        async def timeout(*args, **kwargs):
            raise TimeoutError("uncertain")
        self.client.command.side_effect = timeout
        budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
        try:
            await auto._cave(self.client, self.state, settings(), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertTrue(budget.stopped)
        self.assertIn("uncertain", budget.error)
        self.assertEqual(self.logs.await_args.kwargs["details"]["status"], "uncertain")

    async def test_response_without_finish_time_is_uncertain_and_not_retried(self):
        self.client.command.side_effect = None
        self.client.command.return_value = {
            "state": {**copy.deepcopy(self.state), "stateVersion": self.state["stateVersion"] + 1}}
        await auto._cave(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.logs.await_args.kwargs["details"]["status"], "uncertain")
        self.db.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
