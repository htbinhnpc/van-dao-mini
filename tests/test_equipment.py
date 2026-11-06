import copy
from decimal import Decimal
import unittest
from unittest.mock import AsyncMock, Mock, patch

from api.routes import cleanup as cleanup_routes
from api.services import automation as auto
from api.services.cleanup import CleanupRules, plan_cleanup
from api.services.equipment import (PreparationError, enhanced_vector, plan_normalized_upgrade,
                                    prepare_equipment, transfer_fee, validate_equipment_response, weapon_build)


def gear(item_id, *, enhance=0, location="bag", def_id="equip_t2_weapon", subs=None, **changes):
    return {"id": item_id, "defId": def_id, "slot": "weapon", "location": location,
            "enhance": enhance, "subs": [] if subs is None else subs,
            "locked": False, "favorite": False, **changes}


def snapshot():
    return {"stateVersion": 10, "character": {"level": 70}, "wallet": {"spirit_stone": "10000"},
            "equipment": [gear("worn", enhance=5, location="equipped"),
                          gear("upgrade", subs=[{"stat": "atk", "add": 3}])]}


class NormalizedGearTests(unittest.TestCase):
    def test_compares_unenhanced_upgrade_at_current_enhancement_without_mutating(self):
        state = snapshot(); before = copy.deepcopy(state)
        worn, target = state["equipment"]
        self.assertLess(enhanced_vector(target, auto.META)["add:atk"], enhanced_vector(worn, auto.META)["add:atk"])
        self.assertGreater(enhanced_vector(target, auto.META, 5)["add:atk"], enhanced_vector(worn, auto.META)["add:atk"])
        action = plan_normalized_upgrade(state, auto.META, "weapon")
        self.assertEqual((action["itemId"], action["fromId"], action["enhance"], action["fee"]), ("upgrade", "worn", 5, 30))
        self.assertTrue(action["affordable"])
        self.assertEqual(state, before)

    def test_scales_only_main_and_preserves_add_pct_subs(self):
        item = gear("item", enhance=5, subs=[{"stat": "atk", "add": 2, "pct": .1}, {"stat": "crit", "add": .03}])
        vector = enhanced_vector(item, auto.META)
        self.assertEqual(vector, {"add:atk": Decimal("32.80"), "pct:atk": Decimal(".1"), "add:crit": Decimal(".03")})
        self.assertEqual(enhanced_vector(gear("x2", enhance=5, def_id="x2_eq_001"), auto.META)["add:atk"], Decimal("250.80"))

    def test_better_base_is_selected_even_when_current_raw_stat_is_higher(self):
        state = snapshot(); meta = copy.deepcopy(auto.META)
        meta["equipment"]["equip_t2_weapon"]["main"]["add"] = 8
        meta["equipment"]["equip_t3_weapon"].update(main={"stat": "atk", "add": 9})
        state["equipment"][1].update(defId="equip_t3_weapon", subs=[])
        self.assertEqual(enhanced_vector(state["equipment"][0], meta)["add:atk"], Decimal("11.20"))
        self.assertEqual(enhanced_vector(state["equipment"][1], meta)["add:atk"], Decimal("9"))
        action = plan_normalized_upgrade(state, meta, "weapon")
        self.assertEqual((action["itemId"], action["enhance"]), ("upgrade", 5))

    def test_percent_main_is_not_rounded_or_mixed_with_pct_modifier(self):
        state = snapshot()
        state["equipment"] = [gear("worn", enhance=5, location="equipped", slot="ring", def_id="equip_t2_ring"),
                              gear("upgrade", slot="ring", def_id="equip_t2_ring", subs=[{"stat": "crit", "add": .01}])]
        self.assertEqual(enhanced_vector(state["equipment"][0], auto.META)["add:crit"], Decimal(".056"))
        self.assertEqual(plan_normalized_upgrade(state, auto.META, "ring")["itemId"], "upgrade")

    def test_no_upgrade_for_equal_or_worse_normalized_rolls(self):
        for subs in ([], [{"stat": "atk", "add": -1}]):
            state = snapshot(); state["equipment"][1]["subs"] = subs
            self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))

    def test_tradeoff_never_uses_guessed_stat_weights(self):
        state = snapshot()
        state["equipment"][0]["subs"] = [{"stat": "crit", "add": .1}]
        self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))
        state["equipment"][1]["subs"].append({"stat": "crit", "add": .1})
        self.assertIsNotNone(plan_normalized_upgrade(state, auto.META, "weapon"))

    def test_cannot_lose_an_active_set_bonus(self):
        state = snapshot(); state["equipment"][1]["defId"] = "equip_t3_weapon"
        state["equipment"][1]["subs"] = []
        self.assertIsNotNone(plan_normalized_upgrade(state, auto.META, "weapon"))
        state["equipment"].append(gear("robe", location="equipped", slot="robe", def_id="equip_t2_robe"))
        self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))
        state["equipment"].append(gear("head", location="equipped", slot="head", def_id="equip_t2_head"))
        self.assertIsNotNone(plan_normalized_upgrade(state, auto.META, "weapon"))  # 3 -> 2 keeps bonus.

    def test_keeps_weapon_archetype_not_just_same_magic_stat(self):
        state = snapshot()
        state["equipment"][0]["defId"] = "equip_t2_staff"
        state["equipment"][1].update(defId="equip_t2_lantern", subs=[{"stat": "matk", "add": 3}])
        self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))
        self.assertEqual(weapon_build(auto.META["equipment"]["x2_eq_009"]), "thunder")
        self.assertEqual(weapon_build(auto.META["equipment"]["x2_eq_025"]), "formation")
        self.assertIsNone(weapon_build({"id": "unknown"}))

    def test_never_truncates_existing_enhancement_and_obeys_level(self):
        state = snapshot(); state["equipment"][0]["enhance"] = 9
        self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))  # Target cap +8.
        state = snapshot(); state["character"]["level"] = 7
        self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))
        state["character"] = {}
        self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))

    def test_protected_unknown_duplicate_vault_items_are_not_chosen(self):
        for changes in ({"locked": True}, {"favorite": True}, {"location": "vault"}, {"defId": "unknown"},
                        {"enhance": None}, {"sockets": []}, {"subs": [{"stat": "atk", "add": float("nan")}]}):
            state = snapshot(); state["equipment"][1].update(changes)
            with self.subTest(changes=changes):
                self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))
        for changes in ({"locked": True}, {"favorite": True}):
            state = snapshot(); state["equipment"][0].update(changes)
            self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))
        state = snapshot(); state["equipment"].append(copy.deepcopy(state["equipment"][1]))
        self.assertIsNone(plan_normalized_upgrade(state, auto.META, "weapon"))

    def test_fee_is_preflighted_not_inferred_from_missing_wallet(self):
        for wallet in ({}, {"spirit_stone": "29"}, {"spirit_stone": True}):
            state = snapshot(); state["wallet"] = wallet
            self.assertFalse(plan_normalized_upgrade(state, auto.META, "weapon")["affordable"])
        self.assertEqual(transfer_fee(auto.META["equipment"]["equip_t2_weapon"], 5), 30)
        self.assertEqual(transfer_fee(auto.META["equipment"]["x2_eq_001"], 5), 2200)
        self.assertIsNone(transfer_fee({"cm": True}, 5))

    def test_highest_compatible_donor_is_transferred_only_once(self):
        state = snapshot(); state["equipment"].append(gear("donor", enhance=7))
        action = plan_normalized_upgrade(state, auto.META, "weapon")
        self.assertEqual((action["itemId"], action["fromId"], action["enhance"], action["fee"]), ("upgrade", "donor", 7, 56))

    def test_no_downgrade_when_growth_rates_cross_at_higher_donor_level(self):
        state = snapshot(); meta = copy.deepcopy(auto.META)
        meta["equipment"]["equip_t2_weapon"].update(main={"stat": "atk", "add": 100}, maxEnhance=20)
        meta["equipment"]["x2_eq_001"].update(main={"stat": "atk", "add": 130})
        state["equipment"][0]["enhance"] = 10
        state["equipment"][1].update(defId="x2_eq_001", subs=[])
        state["wallet"]["spirit_stone"] = "1000000000"
        self.assertEqual(plan_normalized_upgrade(state, meta, "weapon")["itemId"], "upgrade")
        state["equipment"].append(gear("donor", enhance=15))
        self.assertIsNone(plan_normalized_upgrade(state, meta, "weapon"))


class NormalizedPreparationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.state = snapshot()
        self.calls = []

    async def send(self, current, name, payload, label):
        self.calls.append((name, payload))
        after = copy.deepcopy(current); after["stateVersion"] += 1
        by_id = {item["id"]: item for item in after["equipment"]}
        if name == "equip":
            target = by_id[payload["itemId"]]
            for item in by_id.values():
                if item["slot"] == target["slot"] and item["location"] == "equipped":
                    item["location"] = "bag"
            target["location"] = "equipped"
        elif name == "item.transfer":
            source, target = by_id[payload["fromId"]], by_id[payload["toId"]]
            after["wallet"]["spirit_stone"] = str(int(after["wallet"]["spirit_stone"]) - transfer_fee(auto.META["equipment"][target["defId"]], source["enhance"]))
            source["enhance"], target["enhance"] = target["enhance"], source["enhance"]
        elif name == "item.dispose":
            after["equipment"] = [item for item in after["equipment"] if item["id"] not in payload["itemIds"]]
        elif name != "equip.best":
            self.fail(f"Unexpected command: {name}")
        return after

    async def test_native_bias_is_corrected_then_transfer_then_disposal_plan(self):
        before = copy.deepcopy(self.state)
        after = await prepare_equipment(self.state, auto.META, self.send)
        self.assertEqual(self.calls, [("equip.best", {}), ("equip", {"itemId": "upgrade"}),
                                     ("item.transfer", {"fromId": "worn", "toId": "upgrade"})])
        self.assertEqual(after["equipment"][1]["enhance"], 5)
        self.assertEqual(after["equipment"][0]["enhance"], 0)
        self.assertEqual([item["id"] for item in plan_cleanup(after, CleanupRules(), auto.META)["items"]], ["worn"])
        self.assertEqual(before, self.state)

    async def test_no_fee_transfer_until_choice_and_no_duplicate_transfer(self):
        self.state["equipment"].append(gear("donor", enhance=7))
        after = await prepare_equipment(self.state, auto.META, self.send)
        transfers = [payload for name, payload in self.calls if name == "item.transfer"]
        self.assertEqual(transfers, [{"fromId": "donor", "toId": "upgrade"}])
        self.assertEqual(after["equipment"][1]["enhance"], 7)

    async def test_insufficient_fee_aborts_before_equip_and_before_disposal(self):
        self.state["wallet"]["spirit_stone"] = "29"
        with self.assertRaises(PreparationError) as raised:
            await prepare_equipment(self.state, auto.META, self.send)
        self.assertEqual(self.calls, [("equip.best", {})])
        self.assertEqual(raised.exception.state["equipment"][0]["location"], "equipped")

    async def test_budget_reserves_both_equip_and_transfer_before_switching(self):
        ensure = Mock(side_effect=auto.PreparationDeferred("deferred"))
        with self.assertRaises(PreparationError):
            await prepare_equipment(self.state, auto.META, self.send, ensure_budget=ensure)
        ensure.assert_called_once_with(2)
        self.assertEqual(self.calls, [("equip.best", {})])

    async def test_unconfirmed_equip_never_sends_transfer(self):
        async def unchanged(current, name, payload, label):
            self.calls.append((name, payload))
            return {**copy.deepcopy(current), "stateVersion": current["stateVersion"] + 1}
        with self.assertRaises(PreparationError):
            await prepare_equipment(self.state, auto.META, unchanged)
        self.assertEqual([name for name, _ in self.calls], ["equip.best", "equip"])

    async def test_transfer_timeout_keeps_latest_equipped_state_without_retry(self):
        async def timeout(current, name, payload, label):
            if name == "item.transfer":
                self.calls.append((name, payload)); raise TimeoutError("uncertain")
            return await self.send(current, name, payload, label)
        with self.assertRaises(PreparationError) as raised:
            await prepare_equipment(self.state, auto.META, timeout)
        self.assertEqual(raised.exception.state["equipment"][1]["location"], "equipped")
        self.assertEqual(len(self.calls), 3)

    async def test_equip_validator_rejects_other_slot_changes_and_lost_items(self):
        self.state["equipment"].append(gear("robe", slot="robe", location="equipped", def_id="equip_t2_robe"))
        after = await self.send(self.state, "equip", {"itemId": "upgrade"}, "")
        validate_equipment_response(self.state, after, "equip", {"itemId": "upgrade"})
        for change in (lambda value: value["equipment"].pop(),
                       lambda value: value["equipment"][2].__setitem__("location", "bag"),
                       lambda value: value["equipment"][1].__setitem__("enhance", 5)):
            changed = copy.deepcopy(after); change(changed)
            with self.assertRaises(ValueError):
                validate_equipment_response(self.state, changed, "equip", {"itemId": "upgrade"})

    async def test_both_auto_equip_and_auto_cleanup_share_normalization(self):
        for cleanup in (False, True):
            self.calls = []; current = copy.deepcopy(self.state)
            client = AsyncMock()
            async def command(name, payload, *, expected_version):
                nonlocal current
                self.assertEqual(expected_version, current["stateVersion"])
                current = await self.send(current, name, payload, "")
                return {"state": current}
            client.command.side_effect = command
            with patch.object(auto, "log", AsyncMock()), patch.object(auto, "patch_rows", AsyncMock(return_value=[{}])):
                handler = auto._cleanup if cleanup else auto._equipment
                result = await handler(client, copy.deepcopy(self.state), {"autoCleanup": cleanup, "autoEquipBest": not cleanup}, {"id": "a"})
            self.assertEqual([name for name, _ in self.calls], ["equip.best", "equip", "item.transfer"] + (["item.dispose"] if cleanup else []))
            worn = next(item for item in result["equipment"] if item["location"] == "equipped")
            self.assertEqual((worn["id"], worn["enhance"]), ("upgrade", 5))

    async def test_auto_budget_defers_before_equip_if_two_steps_will_not_fit(self):
        client = AsyncMock()
        async def command(name, payload, **kwargs):
            return {"state": await self.send(self.state, name, payload, "")}
        client.command.side_effect = command
        budget = auto.TickBudget(attempts=10); token = auto._tick_budget.set(budget)
        try:
            with patch.object(auto, "log", AsyncMock()), patch.object(auto, "patch_rows", AsyncMock(return_value=[{}])):
                await auto._equipment(client, self.state, {"autoEquipBest": True}, {"id": "a"})
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual(self.calls, [("equip.best", {})])
        self.assertTrue(budget.stopped)
        self.assertIsNone(budget.error)

    async def test_auto_timeout_stops_later_cleanup_without_retry(self):
        client = AsyncMock()
        async def command(name, payload, **kwargs):
            if name == "equip":
                raise TimeoutError("uncertain")
            return {"state": await self.send(self.state, name, payload, "")}
        client.command.side_effect = command
        budget = auto.TickBudget(); token = auto._tick_budget.set(budget)
        try:
            with patch.object(auto, "log", AsyncMock()), patch.object(auto, "patch_rows", AsyncMock(return_value=[{}])):
                state = await auto._equipment(client, self.state, {"autoEquipBest": True}, {"id": "a"})
                await auto._cleanup(client, state, {"autoCleanup": True}, {"id": "a"})
        finally:
            auto._tick_budget.reset(token)
        self.assertEqual([call.args[0] for call in client.command.await_args_list], ["equip.best", "equip"])
        self.assertTrue(budget.stopped)
        self.assertIn("uncertain", budget.error)

    async def test_manual_cleanup_preview_uses_same_normalization_and_new_policy_version(self):
        current = copy.deepcopy(self.state)
        client = AsyncMock(); client.get_state.return_value = copy.deepcopy(current)
        async def command(name, payload, *, expected_version):
            nonlocal current
            self.assertEqual(expected_version, current["stateVersion"])
            current = await self.send(current, name, payload, "")
            return {"state": current}
        client.command.side_effect = command
        insert = AsyncMock(return_value={"id": "11111111-1111-4111-8111-111111111111"})
        with (patch.object(cleanup_routes, "owned_account", AsyncMock(return_value={"id": "a"})),
              patch.object(cleanup_routes, "patch_rows", AsyncMock(return_value=[{}])),
              patch.object(cleanup_routes, "insert_one", insert), patch.object(cleanup_routes, "decrypt_session", return_value="synthetic"),
              patch.object(cleanup_routes, "GameClient", return_value=client)):
            result = await cleanup_routes.preview_cleanup("a", cleanup_routes.PreviewRequest(prepareEquipment=True), {"id": "u"})
        self.assertEqual([item["id"] for item in result["plan"]["items"]], ["worn"])
        run = next(call.args[1] for call in insert.await_args_list if call.args[0] == "automation_runs")
        self.assertEqual(run["cursor"]["type"], "cleanup_v3")


if __name__ == "__main__":
    unittest.main()
