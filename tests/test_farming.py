import unittest
from unittest.mock import AsyncMock, patch

from api.services import automation as auto
from api.services import farming

SPOTS = {
    "low": {"id": "low", "regionId": "r1", "reqLevel": 1, "expPerCycle": 2},
    "mid": {"id": "mid", "regionId": "r1", "reqLevel": 10, "expPerCycle": 50},
    "top": {"id": "top", "regionId": "r2", "reqLevel": 20, "expPerCycle": 500},
    "locked": {"id": "locked", "regionId": "r3", "reqLevel": 5, "expPerCycle": 9999},
    "high": {"id": "high", "regionId": "r2", "reqLevel": 60, "expPerCycle": 90000},
    "x2_spot_hunt_01": {"id": "x2_spot_hunt_01", "regionId": "r1", "reqLevel": 1, "expPerCycle": 7000},
    "spot_puppet_a": {"id": "spot_puppet_a", "regionId": "r1", "reqLevel": 1, "expPerCycle": 8000},
    "zero": {"id": "zero", "regionId": "r1", "reqLevel": 1, "expPerCycle": 0},
}
REGIONS = {"r1", "r2"}
NOW = 10_000_000


def ids(spots):
    return [s["id"] for s in spots]


class RankTests(unittest.TestCase):
    def test_highest_experience_wins_not_recommended_level(self):
        self.assertEqual(ids(farming.rank_spots(SPOTS, REGIONS, 25))[:3], ["top", "mid", "low"])

    def test_level_region_and_special_spots_are_gates(self):
        ranked = ids(farming.rank_spots(SPOTS, REGIONS, 25))
        for excluded in ("high", "locked", "x2_spot_hunt_01", "spot_puppet_a", "zero"):
            self.assertNotIn(excluded, ranked)
        self.assertEqual(ids(farming.rank_spots(SPOTS, REGIONS, 5)), ["low"])

    def test_recent_loss_steps_down_then_retries_after_cooldown(self):
        losses = {"top": {"at": NOW - 1000, "power": 100}}
        self.assertEqual(ids(farming.rank_spots(SPOTS, REGIONS, 25, losses=losses, now_ms=NOW, power=100))[0], "mid")
        later = NOW + farming.LOSS_RETRY_MS
        self.assertEqual(ids(farming.rank_spots(SPOTS, REGIONS, 25, losses=losses, now_ms=later, power=100))[0], "top")

    def test_power_gain_allows_early_retry(self):
        losses = {"top": {"at": NOW - 1000, "power": 100}}
        grown = ids(farming.rank_spots(SPOTS, REGIONS, 25, losses=losses, now_ms=NOW, power=111))
        self.assertEqual(grown[0], "top")
        same = ids(farming.rank_spots(SPOTS, REGIONS, 25, losses=losses, now_ms=NOW, power=105))
        self.assertEqual(same[0], "mid")
        unknown = ids(farming.rank_spots(SPOTS, REGIONS, 25, losses=losses, now_ms=NOW, power=None))
        self.assertEqual(unknown[0], "mid")

    def test_ignoring_losses_when_fallback_disabled(self):
        losses = {"top": {"at": NOW - 1000, "power": 100}}
        ranked = farming.rank_spots(SPOTS, REGIONS, 25, losses=losses, now_ms=NOW, avoid_losses=False)
        self.assertEqual(ids(ranked)[0], "top")

    def test_update_losses_records_clears_and_prunes(self):
        lost = farming.update_losses({}, {"type": "farm", "targetId": "top", "win": False}, now_ms=NOW, power=123)
        self.assertEqual(lost, {"top": {"at": NOW, "power": 123}})
        won = farming.update_losses(lost, {"type": "farm", "targetId": "top", "win": True}, now_ms=NOW + 1, power=123)
        self.assertEqual(won, {})
        other = farming.update_losses(lost, {"type": "seclusion", "win": False}, now_ms=NOW, power=1)
        self.assertEqual(other, lost)
        old = {"x": {"at": NOW - farming.LOSS_RETRY_MS - 1, "power": 1}, "bad": "junk"}
        self.assertEqual(farming.update_losses(old, None, now_ms=NOW, power=1), {})


class ActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = {"id": "a", "automation_data": {}}
        self.db = AsyncMock(return_value=[])
        self.logs = AsyncMock()
        for name, mock in (("patch_rows", self.db), ("log", self.logs)):
            patcher = patch.object(auto, name, mock)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = patch.dict(auto.META, {"spots": SPOTS}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.sent = []
        self.client = AsyncMock()
        self.client.command.side_effect = self.command
        self.config = {"autoActivity": True, "activityType": "farm", "autoFallbackHunt": True}

    async def command(self, name, payload, *, expected_version):
        self.sent.append((name, payload))
        return {"state": {"stateVersion": expected_version + 1}}

    def state(self, **extra):
        return {"stateVersion": 1, "power": 100, "character": {"level": 25},
                "regions": [{"id": "r1", "unlocked": True}, {"id": "r2", "unlocked": True}], **extra}

    async def test_sets_highest_experience_spot(self):
        await auto._activity(self.client, self.state(), self.config, self.account)
        self.assertEqual(self.sent, [("activity.set", {"type": "farm", "targetId": "top"})])

    async def test_no_command_when_already_on_best_spot(self):
        state = self.state(activity={"type": "farm", "targetId": "top", "win": True})
        await auto._activity(self.client, state, self.config, self.account)
        self.assertEqual(self.sent, [])

    async def test_loss_steps_down_and_does_not_ping_pong_back(self):
        lost = self.state(activity={"type": "farm", "targetId": "top", "win": False})
        await auto._activity(self.client, lost, self.config, self.account)
        self.assertEqual(self.sent, [("activity.set", {"type": "farm", "targetId": "mid"})])
        self.assertIn("top", self.account["automation_data"]["farmSpotLosses"])
        self.sent.clear()
        winning = self.state(activity={"type": "farm", "targetId": "mid", "win": True})
        await auto._activity(self.client, winning, self.config, self.account)
        self.assertEqual(self.sent, [])  # stays on mid while top's loss is fresh

    async def test_everything_lost_falls_back_to_seclusion(self):
        now = int(__import__("time").time() * 1000)
        self.account["automation_data"] = {"farmSpotLosses": {s: {"at": now, "power": 100} for s in ("top", "mid", "low")}}
        await auto._activity(self.client, self.state(), self.config, self.account)
        self.assertEqual(self.sent, [("activity.set", {"type": "seclusion"})])

    async def test_pinned_spot_and_disabled_fallback(self):
        await auto._activity(self.client, self.state(), {**self.config, "huntSpotId": "mid"}, self.account)
        self.assertEqual(self.sent[-1], ("activity.set", {"type": "farm", "targetId": "mid"}))
        lost = self.state(activity={"type": "farm", "targetId": "top", "win": False})
        self.sent.clear()
        await auto._activity(self.client, lost, {**self.config, "autoFallbackHunt": False}, self.account)
        self.assertEqual(self.sent, [])  # stays on top, no step-down requested

    async def test_off_without_auto_activity(self):
        await auto._activity(self.client, self.state(), {"activityType": "farm"}, self.account)
        self.assertEqual(self.sent, [])


if __name__ == "__main__":
    unittest.main()
