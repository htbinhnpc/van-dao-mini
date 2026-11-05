import copy
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.routes.accounts import DEFAULT_CONFIG
from api.routes.dashboard import CommandRequest, _config_for_update, send_command
from api.services import arena
from api.services import automation as auto
from api.services.game_client import ALLOWED_COMMANDS


def foe(cid, power, rating=1000, same=True):
    return {"characterId": cid, "name": cid, "power": power, "rating": rating, "sameBracket": same}


def board(*opponents, left=10, history=None):
    return {"rankedLeft": left, "opponents": list(opponents), "history": history or []}


class PickOpponentTests(unittest.TestCase):
    def test_requires_power_lead_of_at_least_edge(self):
        a = board(foe("close", 96_000), foe("exact", 95_000), foe("strong", 120_000))
        self.assertEqual(arena.pick_opponent(a, 100_000, min_edge=5000)["characterId"], "exact")
        self.assertIsNone(arena.pick_opponent(board(foe("close", 95_001)), 100_000, min_edge=5000))

    def test_prefers_largest_margin_then_rating(self):
        a = board(foe("a", 80_000, 900), foe("b", 70_000, 800), foe("c", 70_000, 1200))
        self.assertEqual(arena.pick_opponent(a, 100_000)["characterId"], "c")

    def test_ignores_other_bracket_missing_ids_and_bad_power(self):
        a = board(foe("other", 1, same=False), {"characterId": "", "power": 1, "sameBracket": True},
                  foe("nan", float("nan")), {"characterId": "txt", "power": "abc", "sameBracket": True},
                  {"characterId": "bool", "power": True, "sameBracket": True}, "junk",
                  {"characterId": "ok", "power": "10", "sameBracket": True})
        self.assertEqual(arena.pick_opponent(a, 100_000)["characterId"], "ok")

    def test_recent_loss_is_avoided_but_expires(self):
        a = board(foe("lost", 1), foe("next", 50_000))
        picked = arena.pick_opponent(a, 100_000, avoid={"lost": 1_000}, now_ms=2_000)
        self.assertEqual(picked["characterId"], "next")
        picked = arena.pick_opponent(board(foe("lost", 1)), 100_000, avoid={"lost": 1_000},
                                     now_ms=1_000 + arena.LOSS_AVOID_MS)
        self.assertEqual(picked["characterId"], "lost")

    def test_power_and_remaining_runs_are_strict(self):
        for value in (None, 0, -1, "x", True, float("inf")):
            self.assertIsNone(arena.my_power({"power": value}))
        self.assertEqual(arena.my_power({"power": "18940"}), 18940)
        self.assertEqual(arena.ranked_left({"rankedLeft": -3}), 0)
        self.assertEqual(arena.ranked_left({"rankedLeft": 4}), 4)

    def test_last_fight_lost_reads_newest_entry_only(self):
        hist = [{"attacker": True, "opponentId": "x", "won": False},
                {"attacker": True, "opponentId": "x", "won": True}]
        self.assertTrue(arena.last_fight_lost({"history": hist}, "x"))
        self.assertFalse(arena.last_fight_lost({"history": hist[1:]}, "x"))
        self.assertFalse(arena.last_fight_lost({"history": [{"attacker": False, "opponentId": "x", "won": False}]}, "x"))


class ConfigTests(unittest.IsolatedAsyncioTestCase):
    def test_default_off_and_bounded(self):
        self.assertIs(DEFAULT_CONFIG["autoArena"], False)
        self.assertEqual(DEFAULT_CONFIG["arenaMinPowerEdge"], 5000)
        config = _config_for_update({}, {"arenaMinPowerEdge": -5, "arenaMaxRefresh": 99, "arenaMaxFights": 0})
        self.assertEqual((config["arenaMinPowerEdge"], config["arenaMaxRefresh"], config["arenaMaxFights"]), (0, 10, 1))
        with self.assertRaises(HTTPException):
            _config_for_update({}, {"autoArena": "true"})
        with self.assertRaises(HTTPException):
            _config_for_update({}, {"arenaMinPowerEdge": 1.5})

    async def test_arena_command_is_allowlisted_for_auto_but_blocked_for_manual(self):
        self.assertIn("arena.fight", ALLOWED_COMMANDS)
        with self.assertRaises(HTTPException) as error:
            await send_command("a", CommandRequest(command="arena.fight", payload={"defenderId": "x", "ranked": False}),
                               {"id": "u"})
        self.assertEqual(error.exception.status_code, 400)


class ArenaAutomationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = {"id": "acc", "enabled": True, "automation_data": {}}
        self.state = {"stateVersion": 10, "power": 100_000, "character": {"level": 30}}
        self.config = {"autoArena": True, "arenaMinPowerEdge": 5000, "arenaMaxRefresh": 2, "arenaMaxFights": 3}
        self.logs, self.db = AsyncMock(), AsyncMock(return_value=[])
        for name, mock in (("log", self.logs), ("patch_rows", self.db)):
            patcher = patch.object(auto, name, mock)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.boards = {}
        self.reads = []
        self.fought = []
        self.won = True
        self.client = AsyncMock()
        self.client.get_arena.side_effect = self.get_arena
        self.client.command.side_effect = self.command

    async def get_arena(self, pick):
        self.reads.append(pick)
        return copy.deepcopy(self.boards.get(pick, self.boards[max(self.boards)]))

    async def command(self, name, payload, *, expected_version):
        self.assertEqual(name, "arena.fight")
        self.assertIs(payload["ranked"], True)
        self.assertEqual(expected_version, self.state["stateVersion"])
        self.fought.append(payload["defenderId"])
        self.state = {**self.state, "stateVersion": self.state["stateVersion"] + 1}
        for b in self.boards.values():
            b["rankedLeft"] -= 1
            b["history"] = [{"attacker": True, "opponentId": payload["defenderId"], "won": self.won}]
        return {"state": self.state,
                "result": {"won": self.won, "ratingDelta": 12 if self.won else -8, "rating": 1012, "tokens": 10}}

    async def run_arena(self, config=None):
        return await auto._arena(self.client, self.state, config or self.config, self.account)

    async def test_off_by_default_and_requires_level_ten(self):
        self.boards = {0: board(foe("weak", 1))}
        await auto._arena(self.client, self.state, {}, self.account)
        low = {**self.state, "character": {"level": 9}}
        await auto._arena(self.client, low, self.config, self.account)
        self.client.get_arena.assert_not_awaited()
        self.client.command.assert_not_awaited()

    async def test_fights_qualified_opponent_with_ranked_true(self):
        self.boards = {0: board(foe("strong", 99_000), foe("weak", 60_000), left=1)}
        await self.run_arena()
        self.assertEqual(self.fought, ["weak"])
        self.assertEqual(self.reads[0], 0)
        details = self.logs.await_args_list[-1].kwargs["details"]
        self.assertEqual((details["defenderId"], details["powerEdge"], details["won"]), ("weak", 40_000, True))

    async def test_refreshes_until_qualified_opponent_found(self):
        self.boards = {0: board(foe("a", 99_000), left=1), 1: board(foe("b", 98_000), left=1),
                       2: board(foe("c", 50_000), left=1)}
        await self.run_arena()
        self.assertEqual(self.reads[:3], [0, 1, 2])
        self.assertEqual(self.fought, ["c"])

    async def test_no_candidate_after_refresh_limit_does_not_fight_and_idles(self):
        self.boards = {n: board(foe(f"p{n}", 99_000 + n)) for n in range(5)}
        state = await self.run_arena()
        self.assertEqual(self.reads, [0, 1, 2])
        self.client.command.assert_not_awaited()
        self.assertIs(state, self.state)
        self.assertGreater(self.account["automation_data"]["arenaIdleUntil"], 0)
        self.client.get_arena.reset_mock()
        await self.run_arena()
        self.client.get_arena.assert_not_awaited()

    async def test_stops_when_no_ranked_runs_left(self):
        self.boards = {0: board(foe("weak", 1), left=0)}
        await self.run_arena()
        self.client.command.assert_not_awaited()
        self.assertIn("arenaIdleUntil", self.account["automation_data"])

    async def test_unknown_power_never_fights(self):
        self.boards = {0: board(foe("weak", 1))}
        for power in (None, 0, "x"):
            self.state["power"] = power
            self.account["automation_data"] = {}
            await self.run_arena()
        self.client.command.assert_not_awaited()
        self.client.get_arena.assert_not_awaited()

    async def test_respects_max_fights_and_loss_is_remembered(self):
        self.won = False
        self.boards = {0: board(foe("a", 10_000), foe("b", 20_000), left=5)}
        await self.run_arena({**self.config, "arenaMaxFights": 2})
        self.assertEqual(self.fought, ["a", "b"])
        self.assertIn("a", self.account["automation_data"]["arenaLostAt"])

    async def test_command_failure_stops_without_more_fights(self):
        self.boards = {0: board(foe("a", 10_000), foe("b", 20_000), left=5)}
        self.client.command.side_effect = RuntimeError("timeout")
        state = await self.run_arena()
        self.assertEqual(self.client.command.await_count, 1)
        self.assertIs(state, self.state)

    async def test_board_read_error_is_logged_and_no_command_sent(self):
        self.client.get_arena.side_effect = RuntimeError("boom")
        await self.run_arena()
        self.client.command.assert_not_awaited()
        self.assertEqual(self.logs.await_args.args[1], "warning")


if __name__ == "__main__":
    unittest.main()
