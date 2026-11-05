import unittest
from unittest.mock import AsyncMock, patch

from api.routes.accounts import DEFAULT_CONFIG
from api.routes.dashboard import _config_for_update
from api.services import automation as auto
from api.services import encounters as enc
from api.services.game_client import ALLOWED_COMMANDS


def state(*defs, materials=None, wallet=None):
    return {"stateVersion": 1, "materials": materials or {}, "wallet": wallet or {},
            "encounters": [{"id": f"e{i}", "defId": d} for i, d in enumerate(defs)]}


class ChoiceTests(unittest.TestCase):
    def pick(self, def_id, **kw):
        allow = kw.pop("allow_cost", True)
        return enc.pick_choice(enc.ENCOUNTERS[def_id], state(def_id, **kw), allow_cost=allow)

    def test_free_insight_choices_are_preferred(self):
        for def_id in ("enc_old_stele", "enc_sealed_cave", "enc_moonlit_duel"):
            self.assertEqual(self.pick(def_id), "a")

    def test_paid_insight_choice_needs_the_cost(self):
        self.assertEqual(self.pick("enc_dying_cultivator", materials={"item_spirit_pill": 1}), "a")
        self.assertEqual(self.pick("enc_dying_cultivator", materials={"item_spirit_pill": 0}), "b")
        self.assertEqual(self.pick("enc_wounded_crane", materials={"item_spirit_herb": 5}), "a")
        self.assertEqual(self.pick("enc_wounded_crane", materials={"item_spirit_herb": 4}), "b")

    def test_costs_can_be_disallowed(self):
        self.assertEqual(self.pick("enc_dying_cultivator", materials={"item_spirit_pill": 9}, allow_cost=False), "b")
        self.assertEqual(self.pick("enc_wounded_crane", materials={"item_spirit_herb": 9}, allow_cost=False), "b")

    def test_no_insight_encounter_takes_best_free_choice(self):
        self.assertEqual(self.pick("enc_lost_merchant", wallet={"spirit_stone": "999999"}), "a")  # 300 stones, free
        self.assertEqual(self.pick("enc_lost_merchant"), "a")

    def test_unknown_and_malformed_entries_are_never_guessed(self):
        self.assertIsNone(enc.pick_choice(None, {}))
        s = {"encounters": [{"id": "x", "defId": "enc_new"}, {"defId": "enc_old_stele"}, "junk", {"id": "", "defId": "enc_old_stele"}]}
        self.assertEqual(enc.plan(s), [])
        self.assertEqual(enc.have({"materials": {"a": True, "b": "x", "c": float("nan")}}, "a"), 0)

    def test_plan_is_bounded(self):
        s = state("enc_old_stele", "enc_sealed_cave", "enc_moonlit_duel", "enc_old_stele")
        self.assertEqual([p[0] for p in enc.plan(s, limit=3)], ["e0", "e1", "e2"])

    def test_table_matches_client_and_choices_exist(self):
        self.assertEqual(len(enc.ENCOUNTERS), 6)
        self.assertEqual(sum(1 for d in enc.ENCOUNTERS.values() if any("insight" in c for c in d["choices"].values())), 5)


class ConfigTests(unittest.TestCase):
    def test_defaults_and_allowlist(self):
        self.assertIs(DEFAULT_CONFIG["autoEncounter"], False)
        self.assertIs(DEFAULT_CONFIG["encounterAllowCost"], True)
        self.assertIn("encounter.resolve", ALLOWED_COMMANDS)
        self.assertIs(_config_for_update({}, {"autoEncounter": True})["autoEncounter"], True)


class AutomationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = {"id": "a", "automation_data": {}}
        for name in ("log", "patch_rows"):
            patcher = patch.object(auto, name, AsyncMock(return_value=[]))
            patcher.start()
            self.addCleanup(patcher.stop)
        self.sent = []
        self.state = state("enc_old_stele", "enc_dying_cultivator", "enc_lost_merchant", "enc_sealed_cave",
                           materials={"item_spirit_pill": 1})
        self.client = AsyncMock()
        self.client.command.side_effect = self.command

    async def command(self, name, payload, *, expected_version):
        self.sent.append((name, payload))
        remaining = [e for e in self.state["encounters"] if e["id"] != payload["encounterId"]]
        self.state = {**self.state, "stateVersion": expected_version + 1, "encounters": remaining}
        return {"state": self.state}

    async def test_off_by_default(self):
        await auto._encounters(self.client, self.state, {}, self.account)
        self.client.command.assert_not_awaited()

    async def test_resolves_up_to_three_preferring_insight(self):
        await auto._encounters(self.client, self.state, {"autoEncounter": True}, self.account)
        self.assertEqual(self.sent, [("encounter.resolve", {"encounterId": "e0", "choice": "a"}),
                                     ("encounter.resolve", {"encounterId": "e1", "choice": "a"}),
                                     ("encounter.resolve", {"encounterId": "e2", "choice": "a"})])

    async def test_cost_choice_respects_setting(self):
        await auto._encounters(self.client, self.state, {"autoEncounter": True, "encounterAllowCost": False}, self.account)
        self.assertEqual(self.sent[1], ("encounter.resolve", {"encounterId": "e1", "choice": "b"}))

    async def test_never_resends_an_id_the_server_did_not_remove(self):
        async def stubborn(name, payload, *, expected_version):
            self.sent.append((name, payload))
            return {"state": {**self.state, "stateVersion": expected_version + 1}}
        self.client.command.side_effect = stubborn
        await auto._encounters(self.client, self.state, {"autoEncounter": True}, self.account)
        self.assertEqual(len({p["encounterId"] for _, p in self.sent}), len(self.sent))

    async def test_failure_stops_without_retry(self):
        self.client.command.side_effect = RuntimeError("timeout")
        await auto._encounters(self.client, self.state, {"autoEncounter": True}, self.account)
        self.assertEqual(self.client.command.await_count, 1)


if __name__ == "__main__":
    unittest.main()
