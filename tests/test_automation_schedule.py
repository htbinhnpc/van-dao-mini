import copy
import time
import unittest
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.routes import dashboard
from api.routes.accounts import DEFAULT_CONFIG
from api.services import automation as auto
from api.services.automation_schedule import FEATURE_FLAGS, feature_order


def all_enabled():
    return {**DEFAULT_CONFIG, **{flag: True for flags in FEATURE_FLAGS.values() for flag in flags}}


class SchedulePolicyTests(unittest.TestCase):
    def test_only_enabled_groups_run_and_cursor_handles_disabled_and_unknown(self):
        cfg = {"autoUse": True, "autoCraft": True, "autoArena": True}
        self.assertEqual(feature_order(cfg), ["pill", "craft", "arena"])
        self.assertEqual(feature_order(cfg, "craft"), ["craft", "arena", "pill"])
        self.assertEqual(feature_order(cfg, "farm"), ["arena", "pill", "craft"])
        self.assertEqual(feature_order(cfg, "deleted"), feature_order(cfg))
        self.assertEqual(feature_order({"autoSectDonate": True}), [])
        self.assertEqual(feature_order({}, []), [])


class ScheduleWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.account = {"id": "a", "enabled": True, "automation_data": {"other": "keep"}}
        self.state = {"stateVersion": 10}
        self.client = AsyncMock()
        self.visited, self.configs = [], []

    async def work(self, client, state, config, account):
        budget = auto._tick_budget.get()
        self.visited.append((budget.feature_id, state["stateVersion"]))
        self.configs.append(copy.deepcopy(config))
        budget.attempts += 1
        return {**state, "stateVersion": state["stateVersion"] + 1}

    def mock_handlers(self, stack, handler=None):
        for name in ("_claim_ready", "_extra_rewards", "_guild_checkin", "_shared_bosses", "_titles", "_encounters", "_equipment", "_cleanup",
                     "_major_breakthrough", "_minor_trial", "_pets", "_npc", "_use_pill", "_cave", "_craft", "_sect_donation", "_boss", "_farm", "_arena"):
            stack.enter_context(patch.object(auto, name, handler or self.work))

    async def test_many_features_resume_next_tick_without_starving_tail_and_use_latest_state(self):
        cfg = all_enabled()
        with ExitStack() as stack:
            self.mock_handlers(stack)
            visited = []
            for _ in range(2):
                budget = auto.TickBudget(attempts=2)
                token = auto._tick_budget.set(budget)
                try:
                    self.state, summary = await auto._scheduled_features(self.client, self.state, cfg, self.account)
                finally:
                    auto._tick_budget.reset(token)
                visited.extend(row["id"] for row in summary["features"])
                self.account["automation_data"]["automationSchedule"] = {"nextFeature": summary["nextFeature"]}
                self.assertTrue(summary["deferred"])
                self.assertEqual(budget.attempts, 12)
                self.assertIsNone(budget.feature_quota)
        self.assertTrue(set(FEATURE_FLAGS).issubset(visited))
        self.assertEqual([version for _, version in self.visited], list(range(10, 30)))
        self.assertEqual(self.account["automation_data"]["other"], "keep")
        world = next(c for c in self.configs if c.get("autoWorldBoss") and not c.get("autoGuildBoss"))
        guild = next(c for c in self.configs if c.get("autoGuildBoss") and not c.get("autoWorldBoss"))
        self.assertIsNotNone(world); self.assertIsNotNone(guild)

    async def test_small_config_keeps_bulk_work_and_skips_disabled_handlers(self):
        quotas = []
        async def work(*args):
            quotas.append(auto._tick_budget.get().feature_quota)
            return await self.work(*args)
        with ExitStack() as stack:
            self.mock_handlers(stack, work)
            token = auto._tick_budget.set(auto.TickBudget())
            try:
                _, summary = await auto._scheduled_features(self.client, self.state, {"autoCraft": True, "autoArena": True}, self.account)
            finally:
                auto._tick_budget.reset(token)
        self.assertEqual(quotas, [None, None])
        self.assertEqual([r["id"] for r in summary["features"]], ["craft", "arena"])
        self.assertFalse(summary["deferred"])

    async def test_cursor_does_not_dirty_persisted_account_data_before_safety_cas(self):
        original = copy.deepcopy(self.account["automation_data"])
        async def inspect(client, state, config, account):
            self.assertEqual(account["automation_data"], original)
            return state
        with ExitStack() as stack:
            self.mock_handlers(stack, inspect)
            token = auto._tick_budget.set(auto.TickBudget())
            try:
                _, summary = await auto._scheduled_features(self.client, self.state, all_enabled(), self.account)
            finally:
                auto._tick_budget.reset(token)
        self.assertEqual(len(summary["features"]), len(FEATURE_FLAGS))

    async def test_no_handler_or_reads_after_budget_or_time_exhaustion(self):
        for budget in (auto.TickBudget(attempts=12), auto.TickBudget(deadline=time.monotonic() - 1)):
            with ExitStack() as stack:
                self.mock_handlers(stack)
                token = auto._tick_budget.set(budget)
                try:
                    _, summary = await auto._scheduled_features(self.client, self.state, all_enabled(), self.account)
                finally:
                    auto._tick_budget.reset(token)
            self.assertEqual(summary["features"], [])
        self.assertEqual(self.visited, [])

    async def test_unhandled_failure_stops_features_without_retry_and_resets_quota(self):
        failure = AsyncMock(side_effect=TimeoutError("uncertain"))
        with ExitStack() as stack:
            self.mock_handlers(stack, failure)
            budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
            try:
                _, summary = await auto._scheduled_features(self.client, self.state, all_enabled(), self.account)
            finally:
                auto._tick_budget.reset(token)
        self.assertTrue(budget.stopped)
        self.assertIn("uncertain", budget.error)
        self.assertIsNone(budget.feature_quota)
        failure.assert_awaited_once()
        self.assertEqual(len(summary["features"]), 1)

    async def test_claims_obey_soft_quota_and_no_extra_x2_mail_command(self):
        state = {"stateVersion": 10, "quests": [{"id": "q1", "status": "claimable"}, {"id": "q2", "status": "claimable"}],
                 "x2": {"dailyClaimed": False}, "unreadMail": 3}
        self.client.command.return_value = {"state": {**state, "stateVersion": 11}}
        token = auto._tick_budget.set(auto.TickBudget(feature_quota=1))
        try:
            with patch.object(auto, "log", AsyncMock()):
                await auto._claim_ready(self.client, state, {**DEFAULT_CONFIG, "autoX2Daily": True}, self.account)
        finally:
            auto._tick_budget.reset(token)
        self.client.command.assert_awaited_once()

    async def test_npc_and_farm_yield_after_one_independent_command(self):
        for handler, state, cfg in (
            (auto._npc, {"stateVersion": 10, "npcs": [{"id": "elder", "met": True, "talked": False, "affinity": 100, "claimed": []},
                                                       {"id": "friend", "met": True, "talked": False, "affinity": 100, "claimed": []}]},
             {"autoNpcTalk": True, "autoNpcRewards": True}),
            (auto._farm, {"stateVersion": 10, "cave": {"unlocked": True, "plots": 4,
                         "fields": [{"plot": n, "finishAt": 1} for n in range(1, 5)]}}, {"autoFarm": True} )
        ):
            self.client.command.reset_mock()
            self.client.command.return_value = {"state": {**state, "stateVersion": 11}}
            budget = auto.TickBudget(feature_quota=1); token = auto._tick_budget.set(budget)
            try:
                with patch.object(auto, "log", AsyncMock()):
                    await handler(self.client, state, cfg, self.account)
            finally:
                auto._tick_budget.reset(token)
            self.client.command.assert_awaited_once()
            self.assertFalse(budget.stopped)

    async def test_default_manual_tick_also_requires_cron_lease(self):
        run = AsyncMock()
        with (patch.object(dashboard, "owned_account", AsyncMock(return_value={"id": "a"})),
              patch.object(dashboard, "account_config", AsyncMock(return_value=DEFAULT_CONFIG)),
              patch.object(dashboard, "patch_rows", AsyncMock(return_value=[])), patch.object(dashboard, "run_account_tick", run)):
            with self.assertRaises(HTTPException) as raised:
                await dashboard.manual_tick("a", {"id": "u"})
            self.assertEqual(raised.exception.status_code, 409)
        run.assert_not_awaited()
