import copy
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from api.routes import dashboard
from api.routes.accounts import DEFAULT_CONFIG
from api.services import automation as auto
from api.services.community import boss_ready, plan_donation, validate_boss
from api.services.game_client import ALLOWED_COMMANDS, GameAPIError, GameClient


def snapshot():
    return {"stateVersion": 10, "character": {"level": 20, "realm": {"realmId": "truc_co", "stage": 1}},
            "sect": {"id": "sect_thanh_van", "donatedToday": 0}, "guild": {"id": "guild-1"},
            "materials": {"item_iron_ore": 1000, "item_spirit_herb": 500}, "quests": []}


def settings(**changes):
    return {**DEFAULT_CONFIG, "autoSectTasks": True, "autoSectDonate": True, **changes}


def board(**changes):
    return {"bossId": "wb_thunder_serpent", "status": "active", "hp": "99999999999999999999",
            "attemptsLeft": 3, "endsAt": int(time.time() * 1000) + 86400000, **changes}


class CommunityPlannerTests(unittest.TestCase):
    def test_donation_picks_biggest_surplus_and_is_pure(self):
        s = snapshot(); before = copy.deepcopy(s)
        action = plan_donation(s, settings(), auto.META)["action"]
        self.assertEqual((action["itemId"], action["qty"], action["keep"]), ("item_iron_ore", 100, 100))
        self.assertEqual(s, before)

    def test_daily_cap_and_different_item_contribution_values(self):
        s = snapshot(); s["materials"] = {"item_moon_shard": 1000, "item_iron_ore": 150}
        s["sect"]["donatedToday"] = 380
        action = plan_donation(s, settings(), auto.META)["action"]
        self.assertEqual((action["itemId"], action["qty"], action["gain"]), ("item_moon_shard", 1, 16))
        self.assertIsNone(plan_donation(s, settings(sectDonateDaily=380), auto.META)["action"])
        s["sect"]["donatedToday"] = 400
        self.assertIsNone(plan_donation(s, settings(sectDonateDaily=999), auto.META)["action"])

    def test_floor_includes_craft_and_cave_and_allows_only_surplus(self):
        s = snapshot(); s["materials"] = {"item_iron_ore": 222}
        self.assertEqual(plan_donation(s, settings(craftMatFloor=220), auto.META)["action"]["qty"], 2)
        self.assertIsNone(plan_donation(s, settings(autoCaveUpgrade=True, caveMatFloor=222), auto.META)["action"])
        s["materials"]["item_iron_ore"] = 100
        self.assertIsNone(plan_donation(s, settings(), auto.META)["action"])

    def test_reserves_quest_recipe_and_next_major_even_without_auto_craft(self):
        s = snapshot(); s["materials"] = {"item_frost_crystal": 120, "item_core_pill": 1}
        result = plan_donation(s, settings(autoCraft=False), auto.META)
        self.assertIsNone(result["action"])  # 100 floor + 20 directly required by Kết Đan.
        s["materials"]["item_frost_crystal"] = 130
        self.assertEqual(plan_donation(s, settings(), auto.META)["action"]["qty"], 10)
        s["materials"] = {"item_spirit_herb": 103, "item_core_pill": 1}
        s["quests"] = [{"id": "q05_first_craft", "status": "active", "current": 0, "target": 1}]
        self.assertIsNone(plan_donation(s, settings(), auto.META)["action"])

    def test_missing_unknown_invalid_and_non_donatable_inventory_never_spends(self):
        for key, value in (("sect", None), ("materials", None), ("materials", {"item_iron_ore": True}),
                           ("materials", {"unknown": 1000000, "item_qi_pill": 1000000}),
                           ("sect", {"id": "sect_thanh_van"})):
            s = snapshot(); s[key] = value
            with self.subTest(key=key, value=value):
                self.assertIsNone(plan_donation(s, settings(), auto.META)["action"])
        for config in (settings(autoSectTasks=False), settings(autoSectDonate=False), settings(sectDonateDaily=0)):
            self.assertIsNone(plan_donation(snapshot(), config, auto.META)["action"])

    def test_boss_requires_explicit_alive_attempts_expiry_and_level(self):
        now = int(time.time() * 1000)
        self.assertTrue(boss_ready(snapshot(), board(), now_ms=now))
        for change in ({"status": "dead"}, {"hp": "0"}, {"hp": None}, {"attemptsLeft": 0},
                       {"attemptsLeft": True}, {"attemptsLeft": 4}, {"endsAt": now}, {"bossId": None}):
            self.assertFalse(boss_ready(snapshot(), board(**change), now_ms=now))
        s = snapshot(); s["character"]["level"] = 9
        self.assertFalse(boss_ready(s, board(), now_ms=now))

    def test_boss_verification_needs_same_period_and_one_consumed_attempt(self):
        b = board()
        validate_boss(b, {**b, "attemptsLeft": 2, "status": "dead"})
        for change in ({}, {"attemptsLeft": 1}, {"attemptsLeft": 2, "endsAt": b["endsAt"] + 1}):
            with self.assertRaises(ValueError):
                validate_boss(b, {**b, **change})


class CommunityWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = snapshot()
        self.account = {"id": "a", "automation_data": {"other": "keep"}}
        self.client = AsyncMock()
        self.client.command.side_effect = self.command
        self.guild = {"id": "guild-1", "checkedInToday": False}
        self.boards = {scope: board() for scope in ("world", "guild")}
        self.client.get_guild.side_effect = lambda: copy.deepcopy(self.guild)
        self.client.get_worldboss.side_effect = lambda scope: copy.deepcopy(self.boards[scope])
        self.logs, self.db = AsyncMock(), AsyncMock(return_value=[{}])
        for name, value in (("log", self.logs), ("patch_rows", self.db)):
            p = patch.object(auto, name, value); p.start(); self.addCleanup(p.stop)

    async def command(self, name, payload, *, expected_version):
        self.assertEqual(expected_version, self.state["stateVersion"])
        self.assertTrue(self.account["automation_data"]["communityPending"])
        self.state = copy.deepcopy(self.state)
        self.state["stateVersion"] += 1
        if name == "sect.donate":
            from api.services.community import DONATION_VALUES
            self.state["materials"][payload["itemId"]] -= payload["qty"]
            self.state["sect"]["donatedToday"] += payload["qty"] * DONATION_VALUES[payload["itemId"]]
        elif name == "guild.checkin":
            self.guild["checkedInToday"] = True
        elif name == "worldboss.attack":
            self.boards[payload["scope"]]["attemptsLeft"] -= 1
        else:
            self.fail(name)
        return {"state": self.state}

    async def test_disabled_features_neither_read_nor_send_commands(self):
        for handler in (auto._guild_checkin, auto._sect_donation, auto._shared_bosses):
            self.assertIs(await handler(self.client, self.state, DEFAULT_CONFIG, self.account), self.state)
        self.client.command.assert_not_awaited()
        self.client.get_guild.assert_not_awaited()
        self.client.get_worldboss.assert_not_awaited()

    async def test_donate_once_and_replan_from_latest_stock(self):
        result = await auto._sect_donation(self.client, self.state, settings(), self.account)
        self.assertEqual(result["materials"]["item_iron_ore"], 900)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.account["automation_data"], {"other": "keep", "communityPending": {}})
        self.assertEqual(self.db.await_count, 2)  # reserve, then atomic snapshot + unlock
        self.assertIn("state_snapshot", self.db.await_args.args[2])

    async def test_checkin_once_only_with_explicit_unchecked_same_guild(self):
        await auto._guild_checkin(self.client, self.state, settings(autoGuildCheckin=True), self.account)
        await auto._guild_checkin(self.client, self.state, settings(autoGuildCheckin=True), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertTrue(self.guild["checkedInToday"])
        self.assertEqual(self.account["automation_data"]["communityPending"], {})

    async def test_checkin_unknown_missing_membership_and_wrong_guild_skip(self):
        for guild in ({"id": "guild-1"}, {"id": "guild-2", "checkedInToday": False}, None):
            self.guild = guild
            await auto._guild_checkin(self.client, self.state, settings(autoGuildCheckin=True), self.account)
        self.state["guild"] = None
        await auto._guild_checkin(self.client, self.state, settings(autoGuildCheckin=True), self.account)
        self.client.command.assert_not_awaited()

    async def test_both_scopes_once_each_with_latest_version_and_fresh_boards(self):
        result = await auto._shared_bosses(self.client, self.state, settings(autoWorldBoss=True, autoGuildBoss=True), self.account)
        self.assertEqual(result["stateVersion"], 12)
        self.assertEqual([c.args[1] for c in self.client.command.await_args_list], [{"scope": "world"}, {"scope": "guild"}])
        self.assertEqual(self.client.get_worldboss.await_count, 4)
        self.assertEqual(self.account["automation_data"]["communityPending"], {})

    async def test_boss_no_attempts_dead_missing_and_guildless_skip(self):
        for b in (board(attemptsLeft=0), board(status="dead"), None):
            self.boards["world"] = b
            await auto._shared_bosses(self.client, self.state, settings(autoWorldBoss=True), self.account)
        self.state["guild"] = None
        await auto._shared_bosses(self.client, self.state, settings(autoGuildBoss=True), self.account)
        self.client.command.assert_not_awaited()

    async def test_timeout_locks_across_ticks_stops_later_scope_and_does_not_retry(self):
        self.client.command.side_effect = TimeoutError("uncertain")
        budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
        try:
            await auto._shared_bosses(self.client, self.state, settings(autoWorldBoss=True, autoGuildBoss=True), self.account)
            self.assertTrue(budget.stopped)
        finally:
            auto._tick_budget.reset(token)
        self.assertIn("world", self.account["automation_data"]["communityPending"])
        await auto._shared_bosses(self.client, self.state, settings(autoWorldBoss=True), self.account)
        self.assertEqual(self.client.command.await_count, 1)

    async def test_unconfirmed_donation_does_not_unlock_or_retry(self):
        self.client.command.side_effect = None
        self.client.command.return_value = {"state": {**self.state, "stateVersion": 11}}
        await auto._sect_donation(self.client, self.state, settings(), self.account)
        await auto._sect_donation(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertIn("donate", self.account["automation_data"]["communityPending"])

    async def test_missing_boss_postread_locks_even_when_command_returns_state(self):
        self.client.get_worldboss.side_effect = [board(), GameAPIError("offline", status_code=502)]
        await auto._shared_bosses(self.client, self.state, settings(autoWorldBoss=True), self.account)
        self.assertIn("world", self.account["automation_data"]["communityPending"])

    async def test_unconfirmed_checkin_stays_locked(self):
        self.client.get_guild.side_effect = lambda: {"id": "guild-1", "checkedInToday": False}
        await auto._guild_checkin(self.client, self.state, settings(autoGuildCheckin=True), self.account)
        await auto._guild_checkin(self.client, self.state, settings(autoGuildCheckin=True), self.account)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertIn("checkin", self.account["automation_data"]["communityPending"])

    async def test_failed_unlock_write_keeps_in_memory_lock(self):
        self.db.side_effect = [[{}], []]  # lock succeeds, atomic snapshot + unlock fails
        await auto._sect_donation(self.client, self.state, settings(), self.account)
        self.assertIn("donate", self.account["automation_data"]["communityPending"])
        await auto._sect_donation(self.client, self.state, settings(), self.account)
        self.assertEqual(self.client.command.await_count, 1)

    async def test_failed_lock_storage_never_sends_and_exhausted_budget_does_not_read(self):
        self.db.return_value = []
        await auto._sect_donation(self.client, self.state, settings(), self.account)
        self.client.command.assert_not_awaited()
        token = auto._tick_budget.set(auto.TickBudget(attempts=12))
        try:
            await auto._shared_bosses(self.client, self.state, settings(autoWorldBoss=True), self.account)
            self.client.get_worldboss.assert_not_awaited()
        finally:
            auto._tick_budget.reset(token)


class CommunityConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_defaults_off_validation_clamping_and_manual_bypass_block(self):
        for flag in ("autoSectDonate", "autoGuildCheckin", "autoWorldBoss", "autoGuildBoss"):
            self.assertIs(DEFAULT_CONFIG[flag], False)
            with self.assertRaises(HTTPException):
                dashboard._config_for_update({}, {flag: "true"})
        config = dashboard._config_for_update({}, {"sectDonateDaily": 999, "sectDonateMatFloor": -1})
        self.assertEqual((config["sectDonateDaily"], config["sectDonateMatFloor"]), (400, 0))
        for command in ("sect.donate", "guild.checkin", "worldboss.attack"):
            self.assertIn(command, ALLOWED_COMMANDS)
            with self.assertRaises(HTTPException) as raised:
                await dashboard.send_command("a", dashboard.CommandRequest(command=command), {"id": "u"})
            self.assertEqual(raised.exception.status_code, 400)

    async def test_lock_reset_only_explicit_off_and_cas_preserves_other_keys(self):
        account = {"id": "a", "automation_data": {"other": 1, "communityPending": {"world": {"command": "worldboss.attack"}, "donate": {"command": "sect.donate"}}}}
        for update, clear in (({"autoWorldBoss": False}, True), ({"autoWorldBoss": True}, False), ({"autoDaily": False}, False)):
            db = AsyncMock(return_value=[{}])
            with (patch.object(dashboard, "owned_account", AsyncMock(return_value=account)),
                  patch.object(dashboard, "account_config", AsyncMock(return_value=settings())),
                  patch.object(dashboard, "patch_rows", db), patch.object(dashboard, "insert_one", AsyncMock())):
                await dashboard.save_config("a", dashboard.ConfigUpdate(config=update), {"id": "u"})
            writes = [c for c in db.await_args_list if "automation_data" in c.args[2]]
            self.assertEqual(bool(writes), clear)
            if clear:
                self.assertEqual(writes[0].args[2]["automation_data"], {"other": 1, "communityPending": {"donate": {"command": "sect.donate"}}})
                self.assertIn("automation_data=eq.", writes[0].args[1])
                self.assertIn("lease_until.is.null", writes[0].args[1])

    async def test_new_manual_actions_require_lease(self):
        run = AsyncMock()
        with (patch.object(dashboard, "owned_account", AsyncMock(return_value={"id": "a"})),
              patch.object(dashboard, "account_config", AsyncMock(return_value=settings(autoWorldBoss=True))),
              patch.object(dashboard, "patch_rows", AsyncMock(return_value=[])), patch.object(dashboard, "run_account_tick", run)):
            with self.assertRaises(HTTPException) as raised:
                await dashboard.manual_tick("a", {"id": "u"})
            self.assertEqual(raised.exception.status_code, 409)
        run.assert_not_awaited()

    async def test_reset_cannot_unlock_when_off_save_fails_or_worker_is_leased(self):
        account = {"id": "a", "automation_data": {"communityPending": {"world": {"command": "worldboss.attack"}}}}
        for responses in ([], [[{}], [{}], []]):
            db = AsyncMock(return_value=[]) if not responses else AsyncMock(side_effect=responses)
            with (patch.object(dashboard, "owned_account", AsyncMock(return_value=account)),
                  patch.object(dashboard, "account_config", AsyncMock(return_value=settings())),
                  patch.object(dashboard, "patch_rows", db)):
                with self.assertRaises(HTTPException):
                    await dashboard.save_config("a", dashboard.ConfigUpdate(config={"autoWorldBoss": False}), {"id": "u"})
            self.assertIn("world", account["automation_data"]["communityPending"])

    async def test_reset_major_and_community_locks_in_one_cas(self):
        account = {"id": "a", "automation_data": {"other": 1, "majorBreakthroughPending": {"command": "breakthrough.major"},
                                                     "communityPending": {"world": {"command": "worldboss.attack"}}}}
        db = AsyncMock(return_value=[{}])
        with (patch.object(dashboard, "owned_account", AsyncMock(return_value=account)),
              patch.object(dashboard, "account_config", AsyncMock(return_value=settings())),
              patch.object(dashboard, "patch_rows", db), patch.object(dashboard, "insert_one", AsyncMock())):
            await dashboard.save_config("a", dashboard.ConfigUpdate(config={"autoMajorBreakthrough": False, "autoWorldBoss": False}), {"id": "u"})
        writes = [c for c in db.await_args_list if "automation_data" in c.args[2]]
        self.assertEqual(len(writes), 1)
        self.assertEqual(writes[0].args[2]["automation_data"], {"other": 1, "communityPending": {}})

    async def test_read_endpoints_validate_response_and_scope_before_network(self):
        client = GameClient(cookie="mock")
        with patch.object(client, "_request", AsyncMock(return_value={"boss": board()})) as request:
            self.assertEqual((await client.get_worldboss("guild"))["attemptsLeft"], 3)
            request.assert_awaited_once_with("GET", "/api/worldboss?scope=guild")
            with self.assertRaises(ValueError):
                await client.get_worldboss("admin")
            self.assertEqual(request.await_count, 1)
        for response in ({}, {"boss": []}):
            with patch.object(client, "_request", AsyncMock(return_value=response)):
                with self.assertRaises(GameAPIError):
                    await client.get_worldboss("world")
        with patch.object(client, "_request", AsyncMock(return_value={"guild": None})):
            self.assertIsNone(await client.get_guild())
