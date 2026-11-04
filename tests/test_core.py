import os
import unittest
import asyncio
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.index import app
from api.security import hash_password, verify_password
from api.services.game_client import ALLOWED_COMMANDS, GameClient
from api.services.session_crypto import decrypt_session, encrypt_session
from api.routes.dashboard import get_state


class SecurityTests(unittest.TestCase):
    def test_password_hash_round_trip(self):
        encoded = hash_password("correct horse battery staple")
        self.assertNotEqual(encoded, "correct horse battery staple")
        self.assertTrue(verify_password("correct horse battery staple", encoded))
        self.assertFalse(verify_password("wrong password", encoded))

    def test_game_session_encryption_round_trip(self):
        with patch.dict(os.environ, {"SESSION_ENCRYPTION_KEY": "ab" * 32}):
            encrypted = encrypt_session("vd_sid=test-session")
            self.assertNotIn("vd_sid=test-session", str(encrypted))
            self.assertEqual(decrypt_session(encrypted), "vd_sid=test-session")


class ApiTests(unittest.TestCase):
    def test_health_is_public(self):
        response = TestClient(app).get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_protected_route_requires_dashboard_session(self):
        response = TestClient(app).get("/api/v1/dashboard/overview")
        self.assertEqual(response.status_code, 401)

    def test_command_allowlist_contains_readme_commands_only(self):
        self.assertEqual(len(ALLOWED_COMMANDS), 15)
        self.assertNotIn("admin.delete", ALLOWED_COMMANDS)

    def test_non_allowlisted_command_is_rejected_before_network(self):
        client = GameClient(cookie="vd_sid=mock")
        with self.assertRaises(ValueError):
            asyncio.run(client.command("admin.delete", {}))

    def test_cached_state_endpoint_uses_owned_account_snapshot(self):
        account = {"state_snapshot": {"stateVersion": 17}}
        with (
            patch("api.routes.dashboard.owned_account", new=AsyncMock(return_value=account)),
            patch("api.routes.dashboard.account_config", new=AsyncMock(return_value={"enabled": False})),
        ):
            result = asyncio.run(get_state("account-1", False, {"id": "user-1"}))
        self.assertEqual(result["state"]["stateVersion"], 17)
        self.assertEqual(result["config"], {"enabled": False})


if __name__ == "__main__":
    unittest.main()
