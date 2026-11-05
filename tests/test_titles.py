import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.routes import dashboard
from api.routes.accounts import DEFAULT_CONFIG
from api.services import automation as auto
from api.services.game_client import ALLOWED_COMMANDS
from api.services.titles import plan_title_equip, validate_equip_response


def title(title_id, *, owned=True, earned=True, equipped=False):
    return {"id": title_id, "owned": owned, "earned": earned, "equipped": equipped}


def snapshot(titles=None, *, sect="sect_thanh_van", stats=None, equipment=None):
    return {
        "stateVersion": 10,
        "sect": {"id": sect} if sect else None,
        "stats": {"atk": 925, "matk": 640, "crit": 0.16, "critDmg": 1.65}
        if stats is None else stats,
        "equipment": [] if equipment is None else equipment,
        "ascend": {"titles": titles if titles is not None else [
            title("tru_yeu_su", equipped=True),
            title("kim_ton"),
            title("thien_ton"),
        ]},
    }


def settings(**changes):
    return {**DEFAULT_CONFIG, "autoEquipTitle": True, **changes}


def plan(state=None, config=None, meta=None):
    return plan_title_equip(state or snapshot(), config or settings(), meta or auto.META)


class TitlePlannerTests(unittest.TestCase):
    def test_physical_build_equips_best_damage_title_and_does_not_mutate_state(self):
        state = snapshot(titles=[title("kim_ton"), title("thien_ton")], stats={"crit": 0.5, "critDmg": 2.0})
        before = copy.deepcopy(state)
        result = plan(state)
        self.assertEqual(result["build"], "sword")
        self.assertEqual(result["damageStat"], "atk")
        self.assertEqual(result["action"]["titleId"], "thien_ton")
        self.assertEqual(state, before)

    def test_magic_and_body_builds_use_the_matching_damage_stat(self):
        meta = copy.deepcopy(auto.META)
        meta["titles"]["phys_only"] = {"id": "phys_only", "name": "Phys", "mods": [{"stat": "atk", "pct": 0.10}]}
        meta["titles"]["magic_only"] = {"id": "magic_only", "name": "Magic", "mods": [{"stat": "matk", "pct": 0.10}]}
        titles = [title("phys_only"), title("magic_only")]

        self.assertEqual(plan(snapshot(titles, sect="sect_thanh_van"), meta=meta)["action"]["titleId"], "phys_only")
        self.assertEqual(plan(snapshot(titles, sect="sect_thiet_son"), meta=meta)["action"]["titleId"], "phys_only")
        self.assertEqual(plan(snapshot(titles, sect="sect_loi_dinh"), meta=meta)["action"]["titleId"], "magic_only")
        self.assertEqual(plan(snapshot(titles, sect=None,
                                        equipment=[{"slot": "weapon", "location": "equipped",
                                                    "defId": "equip_t1_lantern"}]), meta=meta)["action"]["titleId"],
                         "magic_only")

    def test_crit_score_depends_on_known_crit_stats(self):
        titles = [title("kim_ton"), title("thien_ton")]
        self.assertEqual(plan(snapshot(titles, stats={"crit": 0, "critDmg": 1.5}))["action"]["titleId"], "kim_ton")
        self.assertEqual(plan(snapshot(titles, stats={"crit": 0.5, "critDmg": 2.0}))["action"]["titleId"], "thien_ton")

    def test_missing_crit_stats_blocks_scoring_instead_of_guessing(self):
        result = plan(snapshot([title("kim_ton"), title("thien_ton")], stats={"atk": 100}))
        self.assertEqual(result["phase"], "unknown")
        self.assertIsNone(result["action"])
        self.assertIn("crit", result["reason"])

    def test_no_equip_when_current_title_is_already_best_or_none_add_damage(self):
        current = snapshot([title("kim_ton", equipped=True), title("tru_yeu_su")])
        self.assertIsNone(plan(current)["action"])
        self.assertIn("tốt nhất", plan(current)["reason"])

        defensive = snapshot([title("xao_thu"), title("khai_son_chu")])
        self.assertIsNone(plan(defensive)["action"])
        self.assertIn("tăng sát thương", plan(defensive)["reason"])

    def test_damage_title_replaces_defensive_title_but_ties_do_not_change(self):
        state = snapshot([title("xao_thu", equipped=True), title("kim_ton")])
        self.assertEqual(plan(state)["action"]["titleId"], "kim_ton")
        meta = copy.deepcopy(auto.META)
        meta["titles"]["tie"] = {"id": "tie", "name": "Tie",
                                 "mods": [{"stat": "atk", "pct": 0.01}, {"stat": "matk", "pct": 0.01}]}
        tie = snapshot([title("tru_yeu_su", equipped=True), title("tie")])
        self.assertIsNone(plan(tie, meta=meta)["action"])

    def test_unknown_build_or_incomplete_title_state_sends_nothing(self):
        unknown_build = snapshot([title("kim_ton")], sect=None)
        self.assertEqual(plan(unknown_build)["phase"], "unknown")

        cases = [
            {**snapshot(), "ascend": None},
            {**snapshot(), "ascend": {"titles": [{"id": "kim_ton", "owned": True, "earned": True}]}},
            {**snapshot(), "ascend": {"titles": [title("kim_ton"), title("kim_ton")]}},
            {**snapshot(), "ascend": {"titles": [title("kim_ton", equipped=True), title("tru_yeu_su", equipped=True)]}},
            {**snapshot([title("unknown_title")]), "sect": {"id": "sect_thanh_van"}},
        ]
        for state in cases:
            with self.subTest(state=state["ascend"]):
                result = plan(state)
                self.assertEqual(result["phase"], "unknown")
                self.assertIsNone(result["action"])

    def test_validation_accepts_only_confirmed_target_equip(self):
        before = snapshot([title("kim_ton", equipped=True), title("dai_thien_ton")])
        after = copy.deepcopy(before)
        after["stateVersion"] += 1
        after["ascend"]["titles"][0]["equipped"] = False
        after["ascend"]["titles"][1]["equipped"] = True
        validate_equip_response(before, after, "dai_thien_ton")

        mutations = [
            lambda value: value.__setitem__("stateVersion", before["stateVersion"]),
            lambda value: value["ascend"]["titles"][1].__setitem__("equipped", False),
            lambda value: value["ascend"]["titles"][1].__setitem__("owned", False),
            lambda value: value["ascend"]["titles"][0].__setitem__("equipped", True),
            lambda value: value.__setitem__("ascend", {"titles": []}),
        ]
        for mutate in mutations:
            changed = copy.deepcopy(after)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                validate_equip_response(before, changed, "dai_thien_ton")

    def test_config_defaults_validation_and_allowlist(self):
        self.assertFalse(DEFAULT_CONFIG["autoEquipTitle"])
        for change in ({"autoEquipTitle": "true"}, {"autoEquipTitle": 1}):
            with self.subTest(change=change), self.assertRaises(HTTPException):
                dashboard._config_for_update({}, change)
        self.assertTrue(dashboard._config_for_update({}, {"autoEquipTitle": True})["autoEquipTitle"])
        self.assertIn("title.equip", ALLOWED_COMMANDS)


class TitleWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = snapshot([title("tru_yeu_su", equipped=True), title("dai_thien_ton")])
        self.account = {"id": "a", "automation_data": {"other": "preserved"}}
        self.client = AsyncMock()
        self.client.command.side_effect = self.command
        self.logs = AsyncMock()
        self.db = AsyncMock(return_value=[{}])
        for context in (patch.object(auto, "log", self.logs), patch.object(auto, "patch_rows", self.db)):
            context.start()
            self.addCleanup(context.stop)

    async def command(self, name, payload, *, expected_version):
        self.assertEqual(name, "title.equip")
        self.assertEqual(expected_version, self.state["stateVersion"])
        next_state = copy.deepcopy(self.state)
        next_state["stateVersion"] += 1
        for entry in next_state["ascend"]["titles"]:
            entry["equipped"] = entry["id"] == payload["titleId"]
        self.state = next_state
        return {"state": next_state}

    async def test_worker_sends_exactly_one_confirmed_equip(self):
        result = await auto._titles(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.client.command.await_args.args[1], {"titleId": "dai_thien_ton"})
        self.assertTrue(next(entry for entry in result["ascend"]["titles"]
                             if entry["id"] == "dai_thien_ton")["equipped"])
        self.assertEqual(self.logs.await_args.kwargs["details"]["status"], "succeeded")
        self.assertEqual(self.account["automation_data"]["other"], "preserved")
        self.assertEqual(self.db.await_args.args[2]["state_snapshot"], result)

    async def test_disabled_auto_sends_nothing(self):
        await auto._titles(self.client, self.state, settings(autoEquipTitle=False), self.account)
        self.client.command.assert_not_awaited()

    async def test_timeout_stops_the_tick_without_retry(self):
        async def timeout(*args, **kwargs):
            raise TimeoutError("uncertain")
        self.client.command.side_effect = timeout
        budget = auto.TickBudget()
        token = auto._tick_budget.set(budget)
        try:
            await auto._titles(self.client, self.state, settings(), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertTrue(budget.stopped)
        self.assertIn("uncertain", budget.error)
        self.assertEqual(self.logs.await_args.kwargs["details"]["status"], "uncertain")

    async def test_unconfirmed_response_is_uncertain_and_not_retried(self):
        self.client.command.side_effect = None
        self.client.command.return_value = {
            "state": {**copy.deepcopy(self.state), "stateVersion": self.state["stateVersion"] + 1}}
        budget = auto.TickBudget()
        token = auto._tick_budget.set(budget)
        try:
            await auto._titles(self.client, self.state, settings(), self.account)
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.logs.await_args.kwargs["details"]["status"], "uncertain")
        self.assertTrue(budget.stopped)
        self.db.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
