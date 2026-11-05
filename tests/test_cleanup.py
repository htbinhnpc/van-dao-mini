import asyncio
import copy
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.index import app
from api.routes import cleanup as routes
from api.routes import dashboard
from api.routes.accounts import DEFAULT_CONFIG
from api.routes.dashboard import CommandRequest, _config_for_update, send_command
from api.services import automation
from api.services.cleanup import CleanupRules, config_rules, plan_cleanup
from api.services.equipment import PreparationError, enhancement_cap, prepare_equipment


def gear(item_id, add=0, **patches):
    return {"id": item_id, "defId": "equip_t1_weapon", "slot": "weapon", "location": "bag",
            "enhance": 0, "locked": False, "favorite": False,
            "subs": [{"stat": "atk", "add": add}], **patches}


def state(*items):
    return {"stateVersion": 10, "character": {"level": 20, "autoMinor": True},
            "settings": {"autoSalvageTier": 0, "autoSalvageMode": "salvage"}, "equipment": list(items)}


def selected(snapshot, **rules):
    return [item["id"] for item in plan_cleanup(snapshot, CleanupRules(**rules), automation.META)["items"]]


class PlannerTests(unittest.TestCase):
    def test_skip_confirmation_is_explicit_boolean_and_does_not_enable_automation(self):
        self.assertIs(DEFAULT_CONFIG["cleanupSkipConfirmation"], False)
        config = _config_for_update({}, {"cleanupSkipConfirmation": True})
        self.assertIs(config["autoCleanup"], False)
        self.assertIs(config["enabled"], False)
        for invalid in ("true", 1, None):
            with self.subTest(invalid=invalid), self.assertRaises(HTTPException):
                _config_for_update({}, {"cleanupSkipConfirmation": invalid})
            with self.assertRaises(ValidationError):
                routes.ExecuteRequest(previewId="11111111-1111-4111-8111-111111111111", itemIds=["a"], skipConfirmation=invalid)

    def test_new_cleanup_default_is_off_and_legacy_does_not_enable_it(self):
        self.assertIs(DEFAULT_CONFIG["autoCleanup"], False)
        self.assertIs(_config_for_update({"autoSalvage": True}, {})["autoCleanup"], False)
        config = _config_for_update({"autoSalvage": True}, {"autoCleanup": True})
        self.assertFalse(config["autoSalvage"])
        self.assertEqual(config_rules(config).maxRarity, "dao")
        self.assertEqual(config_rules(config).keepPerDefinition, 0)

    def test_keeps_only_equipped_and_no_spares_even_with_old_config(self):
        snapshot = state(gear("worn", 10, location="equipped"), gear("weak", 3), gear("middle", 5))
        before = copy.deepcopy(snapshot)
        self.assertEqual(selected(snapshot), ["weak", "middle"])
        self.assertEqual(snapshot, before)
        self.assertEqual(selected(snapshot, keepPerDefinition=1), ["weak", "middle"])

    def test_disposes_tradeoffs_and_unique_definitions_not_selected_by_game(self):
        a = gear("atk", 10)
        b = gear("crit", subs=[{"stat": "crit", "add": .2}])
        c = gear("weak", 5)
        self.assertEqual(selected(state(gear("worn", location="equipped"), a, b, c)), ["atk", "crit", "weak"])

    def test_equal_rolls_keep_only_equipped_but_empty_slot_fails_closed(self):
        self.assertEqual(selected(state(gear("first", 5, location="equipped"), gear("second", 5))), ["second"])
        self.assertEqual(selected(state(gear("only", 5))), [])

    def test_never_uses_a_disposed_item_as_the_keeper(self):
        plan = plan_cleanup(state(gear("first", 9, location="equipped"), gear("second", 7), gear("third", 3)), CleanupRules(), automation.META)
        ids = {item["id"] for item in plan["items"]}
        for item in plan["items"]:
            self.assertNotIn(item["keptItemId"], ids)

    def test_different_base_set_and_tier_are_disposed_if_not_equipped(self):
        high = gear("high", 99, defId="equip_t2_weapon")
        low = gear("low", 1)
        self.assertEqual(selected(state(gear("worn", location="equipped"), high, low)), ["high", "low"])

    def test_equipped_locked_favorite_and_enhanced_are_always_retained(self):
        variations = [{"location": "equipped"}, {"locked": True}, {"favorite": True}, {"enhance": 1}]
        for variation in variations:
            with self.subTest(variation=variation):
                snapshot = state(gear("strong", 10, location="equipped"), gear("protected", 1, **variation))
                self.assertNotIn("protected", selected(snapshot))

    def test_only_equipped_items_can_be_keepers(self):
        self.assertEqual(selected(state(gear("equipped", 10, location="equipped"), gear("weak", 1))), ["weak"])
        self.assertEqual(selected(state(gear("vault", 10, location="vault"), gear("weak", 1))), [])

    def test_future_gear_is_not_spared_but_unknown_metadata_is_retained(self):
        snapshot = state(gear("good", 10, location="equipped"), gear("weak", 1, defId="equip_t2_weapon"))
        snapshot["character"]["level"] = 1
        self.assertEqual(selected(snapshot, maxRarity="dao"), ["weak"])
        self.assertEqual(selected(state(gear("good", 10, defId="missing"), gear("weak", 1, defId="missing"))), [])

    def test_missing_or_malformed_flags_and_rolls_fail_closed(self):
        changes = [{"locked": None}, {"favorite": None}, {"enhance": None}, {"enhance": True},
                   {"subs": None}, {"subs": [{"stat": "atk", "add": float("nan")}]},
                   {"subs": [{"stat": "atk", "add": "1e999999"}]},
                   {"subs": [{"stat": [], "add": 1}]}, {"subs": [{"stat": "unknown", "add": 1}]},
                   {"subs": [{"stat": "atk", "add": 1, "effect": "unknown"}]}, {"slot": "robe"},
                   {"sockets": [{"effect": "rare"}]}, {"unknownGameField": 1}]
        for change in changes:
            with self.subTest(change=change):
                self.assertNotIn("bad", selected(state(gear("good", 50, location="equipped"), gear("bad", 1, **change))))
        item = gear("missing", 1); del item["favorite"]
        self.assertEqual(selected(state(gear("good", 50), item)), [])

    def test_duplicate_ids_and_non_dict_entries_never_get_disposed(self):
        snapshot = state(gear("same", 20), gear("same", 2), None, {"id": [], "subs": []})
        self.assertEqual(selected(snapshot), [])
        self.assertEqual(selected({}), [])
        self.assertEqual(selected({"equipment": None}), [])

    def test_rarity_tier_and_slot_filters_are_distinct(self):
        snapshot = state(gear("good", 10, defId="equip_t2_weapon", location="equipped"), gear("weak", 1, defId="equip_t2_weapon"))
        self.assertEqual(selected(snapshot, maxRarity="pham"), [])
        self.assertEqual(selected(snapshot, maxRarity="linh"), ["weak"])
        self.assertEqual(selected(snapshot, maxRarity="linh", maxTier=1), [])
        self.assertEqual(selected(snapshot, maxRarity="linh", slots=["robe"]), [])

    def test_multiple_modifier_entries_and_pct_are_compared_separately(self):
        a = gear("a", location="equipped", subs=[{"stat": "atk", "add": 2}, {"stat": "atk", "add": 3}, {"stat": "hp", "pct": .05}])
        b = gear("b", subs=[{"stat": "atk", "add": 4}, {"stat": "hp", "pct": .04}])
        self.assertEqual(selected(state(a, b)), ["b"])

    def test_batch_limit_does_not_select_its_keepers(self):
        snapshot = state(gear("69", 69, location="equipped"), *[gear(str(i), i) for i in range(69)])
        plan = plan_cleanup(snapshot, CleanupRules(maxItems=20), automation.META)
        self.assertEqual(len(plan["items"]), 20)
        self.assertEqual(plan["candidateCount"], 69)
        self.assertEqual(plan["deferredCount"], 49)
        self.assertNotIn("69", {item["id"] for item in plan["items"]})

    def test_invalid_rules_are_rejected_not_coerced(self):
        changes = [{"mode": "delete"}, {"maxRarity": "bad"}, {"keepPerDefinition": -1}, {"maxItems": 61},
                   {"maxTier": -1}, {"maxItems": True}, {"slots": ["bad"]}, {"slots": ["weapon", "weapon"]}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValidationError):
                CleanupRules(**change)
        with self.assertRaises(HTTPException):
            _config_for_update({}, {"cleanupMaxItems": "20"})


class EquipmentPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def test_game_selects_gear_then_highest_enhance_transfers_before_disposal(self):
        snapshot = state(gear("old", enhance=4, location="equipped"), gear("best", defId="equip_t2_weapon"), gear("other", enhance=2))
        calls = []

        async def send(current, name, payload, label):
            calls.append((name, payload))
            result = copy.deepcopy(current)
            result["stateVersion"] += 1
            by_id = {item["id"]: item for item in result["equipment"]}
            if name == "equip.best":
                by_id["old"]["location"] = "bag"
                by_id["best"]["location"] = "equipped"
            elif name == "item.transfer":
                source, target = by_id[payload["fromId"]], by_id[payload["toId"]]
                source["enhance"], target["enhance"] = target["enhance"], source["enhance"]
            return result

        prepared = await prepare_equipment(snapshot, automation.META, send)
        self.assertEqual(calls, [("equip.best", {}), ("item.transfer", {"fromId": "old", "toId": "best"})])
        self.assertEqual(selected(prepared), ["old", "other"])
        self.assertEqual(prepared["equipment"][1]["enhance"], 4)
        self.assertEqual(snapshot["equipment"][0]["enhance"], 4)

    async def test_failed_or_unconfirmed_transfer_aborts_without_disposal(self):
        snapshot = state(gear("worn", location="equipped"), gear("donor", enhance=3))
        for failure in (TimeoutError("uncertain"), ValueError("not enough stones"), None):
            calls = []

            async def send(current, name, payload, label):
                calls.append(name)
                if name == "item.transfer" and failure:
                    raise failure
                return {**copy.deepcopy(current), "stateVersion": current["stateVersion"] + 1}

            with self.subTest(failure=failure), self.assertRaises(PreparationError):
                await prepare_equipment(snapshot, automation.META, send)
            self.assertEqual(calls, ["equip.best", "item.transfer"])

    async def test_cap_does_not_truncate_donor_and_planner_keeps_it(self):
        snapshot = state(gear("worn", location="equipped"), gear("donor", enhance=8))
        send = AsyncMock(side_effect=lambda current, *args: {**current, "stateVersion": current["stateVersion"] + 1})
        prepared = await prepare_equipment(snapshot, automation.META, send)
        self.assertEqual(send.await_count, 1)
        self.assertEqual(selected(prepared), [])

    async def test_locked_favorite_and_vault_donors_are_not_transferred_or_disposed(self):
        for changes in ({"locked": True}, {"favorite": True}, {"location": "vault"}):
            snapshot = state(gear("worn", location="equipped"), gear("donor", enhance=4, **changes))
            send = AsyncMock(side_effect=lambda current, *args: {**current, "stateVersion": current["stateVersion"] + 1})
            prepared = await prepare_equipment(snapshot, automation.META, send)
            self.assertTrue(all(call.args[1] != "item.transfer" for call in send.await_args_list))
            self.assertEqual(selected(prepared), [])

    async def test_missing_state_and_unchanged_version_abort(self):
        snapshot = state(gear("bag"))
        for response in (None, {}, snapshot, {"stateVersion": 11}):
            with self.subTest(response=response), self.assertRaises(PreparationError):
                await prepare_equipment(snapshot, automation.META, AsyncMock(return_value=response))

    def test_expansion_caps_follow_realm_stage_counts_not_fallback_levels(self):
        definition = automation.META["equipment"]["x2_eq_001"]
        for level, cap in ((15, 0), (16, 5), (23, 5), (24, 10), (42, 15), (58, 15), (59, 20)):
            self.assertEqual(enhancement_cap(definition, {"character": {"level": level}}, automation.META), cap)


class CleanupRouteTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.snapshot = state(gear("keeper", 10, location="equipped"), gear("weak", 2), gear("locked", 1, locked=True))
        self.account = {"id": "account-1", "user_id": "user-1"}
        self.user = {"id": "user-1"}
        self.run = None
        self.calls = []
        self.lease_busy = False
        self.config = {**DEFAULT_CONFIG}
        self.client = AsyncMock()
        self.client.get_state.side_effect = lambda: copy.deepcopy(self.snapshot)
        self.client.command.side_effect = self.command
        self.db = AsyncMock(side_effect=self.db_patch)
        self.inserts = AsyncMock(side_effect=self.insert)
        self.owner = AsyncMock(return_value=self.account)
        self.patches = [patch.object(routes, "owned_account", self.owner),
                        patch.object(routes, "account_config", AsyncMock(side_effect=lambda *args: self.config)),
                        patch.object(routes, "GameClient", return_value=self.client),
                        patch.object(routes, "decrypt_session", return_value="mock"),
                        patch.object(routes, "patch_rows", self.db),
                        patch.object(routes, "insert_one", self.inserts),
                        patch.object(routes, "select_one", AsyncMock(side_effect=lambda *args: copy.deepcopy(self.run)))]
        for context in self.patches:
            context.start(); self.addCleanup(context.stop)

    async def insert(self, table, data):
        if table == "automation_runs":
            self.run = {"id": "11111111-1111-4111-8111-111111111111", **copy.deepcopy(data)}
            return copy.deepcopy(self.run)
        return {"id": 1, **data}

    async def db_patch(self, table, query, values):
        if table == "game_accounts":
            if "or=(lease_until" in query and self.lease_busy:
                return []
            return [{**self.account, **values}]
        if table == "automation_runs":
            if "status=eq.queued" in query and self.run["status"] != "queued":
                return []
            self.run.update(values)
            return [copy.deepcopy(self.run)]
        return []

    async def command(self, name, payload, *, expected_version, idempotency_key=None):
        self.assertEqual(expected_version, self.snapshot["stateVersion"])
        self.calls.append((name, payload))
        if name == "item.dispose":
            self.assertEqual(idempotency_key, self.run["id"])
            self.snapshot["equipment"] = [item for item in self.snapshot["equipment"] if item["id"] not in payload["itemIds"]]
        elif name != "equip.best":
            raise AssertionError(f"Unexpected command: {name}")
        self.snapshot["stateVersion"] += 1
        return {"state": copy.deepcopy(self.snapshot)}

    async def preview(self, **rules):
        result = await routes.preview_cleanup("account-1", routes.PreviewRequest(rules=CleanupRules(**rules), prepareEquipment=True), self.user)
        # Tests below focus on disposal after the equipment preparation phase.
        self.client.command.reset_mock()
        self.calls.clear()
        return result

    def execution(self, ids=None, *, skip=False):
        return routes.ExecuteRequest(previewId=self.run["id"], itemIds=ids or ["weak"], skipConfirmation=skip)

    def audit_logs(self):
        return [call.args[1] for call in self.inserts.await_args_list if call.args[0] == "activity_logs" and call.args[1]["action"] == "cleanup.manual"]

    async def test_explicit_preparation_is_required_and_old_previews_are_rejected(self):
        with self.assertRaises(HTTPException) as error:
            await routes.preview_cleanup("account-1", routes.PreviewRequest(), self.user)
        self.assertEqual(error.exception.status_code, 422)
        self.client.command.assert_not_awaited()
        await self.preview()
        self.run["cursor"]["type"] = "cleanup_v1"
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.client.command.assert_not_awaited()

    async def test_preparation_is_leased_and_preview_uses_confirmed_new_loadout(self):
        result = await routes.preview_cleanup("account-1", routes.PreviewRequest(prepareEquipment=True), self.user)
        self.assertEqual(self.calls, [("equip.best", {})])
        self.assertEqual(result["plan"]["stateVersion"], 11)
        self.assertEqual(result["plan"]["rules"]["keepPerDefinition"], 0)
        self.assertTrue(any("state_snapshot" in call.args[2] for call in self.db.await_args_list))

    async def test_preparation_failure_never_creates_disposal_preview_or_retries(self):
        self.client.command.side_effect = TimeoutError("uncertain")
        with self.assertRaises(HTTPException):
            await routes.preview_cleanup("account-1", routes.PreviewRequest(prepareEquipment=True), self.user)
        self.assertIsNone(self.run)
        self.assertEqual(self.client.command.await_count, 1)

    async def test_quick_cleanup_requires_saved_opt_in_for_this_account(self):
        await self.preview()
        with self.assertRaises(HTTPException) as error:
            await routes.execute_cleanup("account-1", self.execution(skip=True), self.user)
        self.assertEqual(error.exception.status_code, 409)
        with self.assertRaises(HTTPException):
            await routes.preview_cleanup("account-1", routes.PreviewRequest(skipConfirmation=True), self.user)
        self.assertEqual(self.client.get_state.await_count, 1)
        self.client.command.assert_not_awaited()

    async def test_quick_cleanup_logs_intent_before_command_and_precise_result(self):
        self.config["cleanupSkipConfirmation"] = True
        await self.preview(mode="sell")
        original_command = self.command

        async def audited_command(*args, **kwargs):
            self.assertEqual(self.audit_logs()[-1]["details"]["status"], "started")
            return await original_command(*args, **kwargs)

        self.client.command.side_effect = audited_command
        await routes.execute_cleanup("account-1", self.execution(skip=True), self.user)
        logs = self.audit_logs()
        self.assertEqual([entry["details"]["status"] for entry in logs], ["started", "succeeded"])
        details = logs[-1]["details"]
        self.assertEqual(details["confirmation"], "skipped")
        self.assertEqual(details["mode"], "sell")
        self.assertEqual(details["removedIds"], ["weak"])
        self.assertEqual(details["stateVersionBefore"], 11)
        self.assertEqual(details["stateVersionAfter"], 12)
        self.assertEqual(details["items"][0]["keptItemId"], "keeper")
        self.assertIn("không hỏi xác nhận", logs[-1]["message"])

    async def test_revoked_opt_in_and_stale_state_still_block_quick_cleanup(self):
        self.config["cleanupSkipConfirmation"] = True
        await self.preview()
        self.config["cleanupSkipConfirmation"] = False
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(skip=True), self.user)
        self.config["cleanupSkipConfirmation"] = True
        self.snapshot["stateVersion"] += 1
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(skip=True), self.user)
        self.client.command.assert_not_awaited()
        self.assertEqual(self.audit_logs()[-1]["details"]["status"], "blocked")

    async def test_unavailable_intent_log_blocks_command_instead_of_silent_disposal(self):
        await self.preview()
        original_insert = self.insert

        async def fail_intent(table, data):
            if table == "activity_logs" and data["details"]["status"] == "started":
                raise RuntimeError("Audit unavailable")
            return await original_insert(table, data)

        self.inserts.side_effect = fail_intent
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.client.command.assert_not_awaited()
        self.assertEqual(self.audit_logs()[-1]["details"]["status"], "blocked")
        self.assertEqual(self.run["status"], "failed")

    async def test_quick_empty_preview_logs_skip_without_sending_command(self):
        self.config["cleanupSkipConfirmation"] = True
        self.snapshot = state(gear("only", 10, location="equipped"))
        result = await routes.preview_cleanup("account-1", routes.PreviewRequest(skipConfirmation=True, prepareEquipment=True), self.user)
        self.assertIsNone(result["previewId"])
        self.assertEqual(self.audit_logs()[-1]["details"]["status"], "skipped")
        self.client.command.assert_not_awaited()

    async def test_partial_result_logs_exact_removed_and_remaining_ids(self):
        self.snapshot["equipment"].append(gear("another", 1))
        await self.preview()
        next_state = copy.deepcopy(self.snapshot)
        next_state["stateVersion"] += 1
        next_state["equipment"] = [item for item in next_state["equipment"] if item["id"] != "weak"]
        self.client.command.side_effect = None
        self.client.command.return_value = {"state": next_state}
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(["weak", "another"]), self.user)
        details = self.audit_logs()[-1]["details"]
        self.assertEqual(details["status"], "partial")
        self.assertEqual(details["removedIds"], ["weak"])
        self.assertEqual(details["remainingIds"], ["another"])

    async def test_preview_binds_post_preparation_state_rules_ids_and_account(self):
        result = await self.preview()
        self.assertEqual([item["id"] for item in result["plan"]["items"]], ["weak"])
        self.assertEqual(self.run["account_id"], "account-1")
        self.assertEqual(self.run["cursor"]["stateVersion"], 11)
        self.assertEqual(self.run["status"], "queued")
        self.assertGreater(self.run["cursor"]["expiresAt"], time.time())
        self.client.command.assert_not_awaited()

    async def test_empty_preview_does_not_create_an_executable_confirmation(self):
        self.snapshot = state(gear("only", 10))
        result = await self.preview()
        self.assertIsNone(result["previewId"])
        self.assertEqual(result["plan"]["items"], [])
        self.assertIsNone(self.run)
        self.client.command.assert_not_awaited()

    async def test_user_can_dispose_only_a_selected_subset_of_the_preview(self):
        self.snapshot["equipment"].append(gear("another-weak", 1))
        result = await self.preview()
        self.assertEqual(len(result["plan"]["items"]), 2)
        result = await routes.execute_cleanup("account-1", self.execution(["another-weak"]), self.user)
        self.assertEqual(result["removedCount"], 1)
        self.assertIn("weak", [item["id"] for item in result["state"]["equipment"]])
        self.assertEqual(self.run["cursor"]["selectedItemIds"], ["another-weak"])

    async def test_confirmed_execution_is_versioned_and_cannot_be_replayed(self):
        await self.preview(mode="sell")
        result = await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(result["removedCount"], 1)
        self.assertEqual(self.calls, [("item.dispose", {"itemIds": ["weak"], "mode": "sell"})])
        self.assertEqual(self.run["status"], "succeeded")
        self.assertTrue(any(call.args[0] == "activity_logs" for call in self.inserts.await_args_list))
        with self.assertRaises(HTTPException) as error:
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(self.calls), 1)

    async def test_stale_state_rejects_without_mutation(self):
        await self.preview(); self.snapshot["stateVersion"] += 1
        with self.assertRaises(HTTPException) as error:
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.client.command.assert_not_awaited()

    async def test_protection_is_revalidated_even_if_bad_server_reuses_version(self):
        await self.preview(); self.snapshot["equipment"][1]["locked"] = True
        with self.assertRaises(HTTPException) as error:
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.client.command.assert_not_awaited()

    async def test_foreign_protected_or_injected_ids_cannot_be_added(self):
        await self.preview()
        for ids in (["locked"], ["keeper"], ["foreign-id"]):
            with self.subTest(ids=ids), self.assertRaises(HTTPException) as error:
                await routes.execute_cleanup("account-1", self.execution(ids), self.user)
            self.assertEqual(error.exception.status_code, 422)
        self.client.command.assert_not_awaited()

    async def test_expired_preview_and_busy_lease_send_nothing(self):
        await self.preview(); self.run["cursor"]["expiresAt"] = 1
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        await self.preview(); self.lease_busy = True
        with self.assertRaises(HTTPException) as error:
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.client.command.assert_not_awaited()

    async def test_timeout_consumes_confirmation_and_does_not_retry(self):
        await self.preview(); self.client.command.side_effect = TimeoutError("uncertain")
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(self.run["status"], "failed")
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(self.client.command.await_count, 1)
        self.assertEqual(self.audit_logs()[-1]["details"]["status"], "uncertain")
        self.assertNotIn("removedIds", self.audit_logs()[-1]["details"])

    async def test_racing_confirmation_only_the_atomic_winner_sends_game_command(self):
        await self.preview()
        original_patch = self.db.side_effect

        async def already_claimed(table, query, values):
            if table == "automation_runs" and "status=eq.queued" in query:
                self.run["status"] = "running"
                return []
            return await original_patch(table, query, values)

        self.db.side_effect = already_claimed
        with self.assertRaises(HTTPException) as error:
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.client.command.assert_not_awaited()

    async def test_missing_state_and_partial_disposal_are_not_reported_as_success(self):
        await self.preview(); self.client.command.side_effect = None; self.client.command.return_value = {"ok": True}
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(self.run["status"], "failed")
        self.client.command.side_effect = self.command
        await self.preview(); self.client.command.side_effect = None; self.client.command.return_value = {"state": {**self.snapshot, "stateVersion": self.snapshot["stateVersion"] + 1}}
        with self.assertRaises(HTTPException):
            await routes.execute_cleanup("account-1", self.execution(), self.user)
        self.assertEqual(self.run["status"], "partial")

    async def test_owner_is_checked_before_loading_any_preview(self):
        self.owner.side_effect = HTTPException(404, "not owned")
        with self.assertRaises(HTTPException):
            await self.preview()
        self.client.get_state.assert_not_awaited(); self.inserts.assert_not_awaited()

    async def test_unrestricted_command_endpoint_cannot_bypass_cleanup_policy(self):
        with self.assertRaises(HTTPException) as error:
            await send_command("account-1", CommandRequest(command="item.dispose", payload={"itemIds": ["locked"]}), self.user)
        self.assertEqual(error.exception.status_code, 400)
        self.client.command.assert_not_awaited()

    def test_unauthenticated_routes_require_a_dashboard_session(self):
        client = TestClient(app)
        for path in ("preview", "execute"):
            response = client.post(f"/api/v1/accounts/account-1/cleanup/{path}", json={})
            self.assertEqual(response.status_code, 401)


class CleanupConfigTests(unittest.IsolatedAsyncioTestCase):
    async def test_saving_skip_option_only_changes_account_config_and_logs_opt_in(self):
        with patch.object(dashboard, "owned_account", AsyncMock(return_value={"id": "account-1"})), patch.object(dashboard, "account_config", AsyncMock(return_value=DEFAULT_CONFIG.copy())), patch.object(dashboard, "patch_rows", AsyncMock(return_value=[{}])) as updates, patch.object(dashboard, "insert_one", AsyncMock(return_value={})) as logs, patch.object(dashboard, "GameClient") as game:
            result = await dashboard.save_config("account-1", dashboard.ConfigUpdate(config={"cleanupSkipConfirmation": True}), {"id": "u"})
        self.assertIs(result["config"]["cleanupSkipConfirmation"], True)
        self.assertIs(result["config"]["autoCleanup"], False)
        self.assertIn("account_id=eq.account-1", updates.await_args_list[0].args[1])
        self.assertEqual(logs.await_args.args[1]["action"], "cleanup.config")
        self.assertEqual(logs.await_args.args[1]["details"]["status"], "configured")
        game.assert_not_called()


class AutoCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_transfer_failure_stops_before_disposal_and_keeps_last_confirmed_state(self):
        snapshot = state(gear("worn", location="equipped"), gear("donor", enhance=4))
        prepared = {**snapshot, "stateVersion": 11}
        client = AsyncMock()
        client.command.side_effect = [{"state": prepared}, TimeoutError("uncertain")]
        budget = automation.TickBudget()
        token = automation._tick_budget.set(budget)
        try:
            with patch.object(automation, "log", AsyncMock()), patch.object(automation, "patch_rows", AsyncMock()):
                result = await automation._cleanup(client, snapshot, {"autoCleanup": True}, {"id": "a"})
        finally:
            automation._tick_budget.reset(token)
        self.assertEqual([call.args[0] for call in client.command.await_args_list], ["equip.best", "item.transfer"])
        self.assertEqual(result["stateVersion"], 11)
        self.assertTrue(budget.stopped)
        self.assertIn("uncertain", budget.error)

    async def test_budget_exhaustion_during_preparation_never_disposes(self):
        snapshot = state(gear("worn", location="equipped"), gear("donor", enhance=4))
        client = AsyncMock()
        client.command.return_value = {"state": {**snapshot, "stateVersion": 11}}
        budget = automation.TickBudget(attempts=11)
        token = automation._tick_budget.set(budget)
        try:
            with patch.object(automation, "log", AsyncMock()), patch.object(automation, "patch_rows", AsyncMock()):
                result = await automation._cleanup(client, snapshot, {"autoCleanup": True}, {"id": "a"})
        finally:
            automation._tick_budget.reset(token)
        self.assertEqual([call.args[0] for call in client.command.await_args_list], ["equip.best"])
        self.assertEqual(result["stateVersion"], 11)
        self.assertIsNone(budget.error)

    async def test_empty_auto_plan_logs_skip_and_never_sends_command(self):
        client = AsyncMock()
        with patch.object(automation, "log", AsyncMock()) as logs:
            await automation._cleanup(client, state(gear("only", 1, location="equipped")), {"autoCleanup": True}, {"id": "a"})
        client.command.assert_not_awaited()
        self.assertEqual(logs.await_args.kwargs["details"]["status"], "skipped")

    async def test_auto_records_rules_items_and_success_without_per_batch_confirmation(self):
        snapshot = state(gear("keep", 10, location="equipped"), gear("weak", 2))
        client = AsyncMock()
        client.command.side_effect = [{"state": {**snapshot, "stateVersion": 11}}, {"state": state(gear("keep", 10, location="equipped")) | {"stateVersion": 12}}]
        with patch.object(automation, "log", AsyncMock()) as logs, patch.object(automation, "patch_rows", AsyncMock()):
            await automation._cleanup(client, snapshot, {"autoCleanup": True}, {"id": "a"})
        disposal_logs = [call for call in logs.await_args_list if call.args[2] == "item.dispose"]
        self.assertEqual([call.kwargs["details"]["status"] for call in disposal_logs], ["started", "succeeded"])
        details = logs.await_args.kwargs["details"]
        self.assertEqual(details["items"][0]["id"], "weak")
        self.assertEqual(details["confirmation"], "not_required")
        self.assertEqual(details["removedIds"], ["weak"])
        self.assertEqual(details["rules"]["keepPerDefinition"], 0)

    async def test_partial_auto_disposal_keeps_new_state_but_stops_remaining_commands(self):
        old = state(gear("keep", 10), gear("weak", 2))
        new = {**old, "stateVersion": 11}
        client = AsyncMock(); client.command.return_value = {"state": new}
        budget = automation.TickBudget()
        token = automation._tick_budget.set(budget)
        try:
            with patch.object(automation, "log", AsyncMock()):
                result = await automation._best_effort(client, old, "item.dispose", {"itemIds": ["weak"], "mode": "sell"}, {"id": "a"}, "Dọn")
                await automation._best_effort(client, result, "equip.best", {}, {"id": "a"}, "Mặc")
        finally:
            automation._tick_budget.reset(token)
        self.assertIs(result, new)
        self.assertTrue(budget.error)
        self.assertEqual(client.command.await_count, 1)

    async def test_auto_cleanup_disables_native_before_settle_and_sends_one_batch(self):
        snapshot = state(gear("keep", 10, location="equipped"), gear("weak", 2))
        snapshot["settings"]["autoSalvageTier"] = 7
        calls = []
        client = AsyncMock(); client.get_state.return_value = snapshot

        async def command(name, payload, *, expected_version):
            nonlocal snapshot
            self.assertEqual(expected_version, snapshot["stateVersion"])
            calls.append((name, payload)); snapshot = copy.deepcopy(snapshot); snapshot["stateVersion"] += 1
            if name == "settings.set": snapshot["settings"].update(payload)
            if name == "item.dispose": snapshot["equipment"] = [item for item in snapshot["equipment"] if item["id"] not in payload["itemIds"]]
            return {"state": snapshot}

        client.command.side_effect = command
        with patch.object(automation, "GameClient", return_value=client), patch.object(automation, "decrypt_session", return_value="mock"), patch.object(automation, "log", AsyncMock()), patch.object(automation, "patch_rows", AsyncMock(return_value=[])):
            result = await automation.run_account_tick({"id": "account-1", "enabled": True, "config": {"autoCleanup": True, "autoSalvage": True}})
        self.assertTrue(result["completed"])
        self.assertEqual([name for name, _ in calls], ["settings.set", "settle", "equip.best", "item.dispose"])
        self.assertEqual(calls[0][1]["autoSalvageTier"], 0)
        self.assertEqual(calls[-1][1]["itemIds"], ["weak"])

    async def test_disabled_auto_never_disposes(self):
        client = AsyncMock()
        snapshot = state(gear("keep", 10), gear("weak", 2))
        self.assertIs(await automation._cleanup(client, snapshot, DEFAULT_CONFIG, {"id": "a"}), snapshot)
        client.command.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
