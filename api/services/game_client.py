"""Small client for the official game API documented in api_knowledge.md.

It implements login, state reads, and the observed command envelope; automation policy and
account ownership checks belong in the application service layer.
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import httpx

GAME_ORIGIN = os.getenv(
    "GAME_ORIGIN", "https://vandaonghichmenh.hongvan.net:60010"
).rstrip("/")
USER_AGENT = "VanDaoMiniClient/1.0"
ALLOWED_COMMANDS = frozenset(
    {
        "settle",
        "settings.set",
        "activity.set",
        "quest.claim",
        "daily.claim",
        "weekly.claim",
        "achievement.claim",
        "mail.claimAll",
        "x2.daily.claim",
        "craft.start",
        "cave.upgrade",
        "item.use",
        "boss.fight",
        "field.plant",
        "field.harvest",
        "field.rush",
        "equip.best",
        "item.transfer",
        "minor.trial",
        "sect.task.claim",
        "season.task.claim",
        "title.claim",
        "title.equip",
        "pet.adopt",
        "npc.talk",
        "npc.claim",
        "hunt.run",
        "item.dispose",
        "arena.fight",
        "encounter.resolve",
    }
)


class GameAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class GameClient:
    def __init__(self, *, cookie: str | None = None, timeout: float = 25.0):
        self.cookie = cookie
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {
            "Origin": GAME_ORIGIN,
            "Referer": f"{GAME_ORIGIN}/",
            "User-Agent": USER_AGENT,
        }
        if self.cookie:
            headers["Cookie"] = self.cookie
        return headers

    async def get_maintenance(self) -> dict[str, Any]:
        """Read public server maintenance status; this endpoint needs no session."""
        async with httpx.AsyncClient(timeout=min(self.timeout, 10.0)) as client:
            response = await client.get(
                f"{GAME_ORIGIN}/api/maintenance",
                headers={
                    "Origin": GAME_ORIGIN,
                    "Referer": f"{GAME_ORIGIN}/",
                    "User-Agent": USER_AGENT,
                },
            )
        data = self._json(response)
        if not response.is_success or data.get("ok") is False:
            self._raise(response, data)
        return data

    async def login(self, username: str, password: str) -> str:
        """Login through the game's official endpoint and return vd_sid cookie."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{GAME_ORIGIN}/api/auth/login",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={"username": username, "password": password, "remember": True},
            )
        data = self._json(response)
        if not response.is_success or data.get("ok") is False:
            self._raise(response, data)
        session_id = response.cookies.get("vd_sid")
        if not session_id:
            raise GameAPIError(
                "Game login did not set the vd_sid session cookie.",
                status_code=502,
            )
        return f"vd_sid={session_id}"

    async def get_state(self) -> dict[str, Any]:
        data = await self._request("GET", "/api/state")
        state = data.get("state")
        if not isinstance(state, dict):
            raise GameAPIError("Game API response is missing state.", status_code=502)
        return state

    async def get_arena(self, pick: int = 0) -> dict[str, Any]:
        """Read the arena board; ``pick`` is the game's refresh counter (a new value redraws opponents)."""
        data = await self._request("GET", f"/api/arena?pick={max(0, int(pick))}")
        arena = data.get("arena")
        if not isinstance(arena, dict):
            raise GameAPIError("Game API response is missing arena.", status_code=502)
        return arena

    async def command(
        self,
        command: str,
        payload: dict[str, Any] | None = None,
        *,
        expected_version: int = 1,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """Send one allowlisted official command; no automatic retry is done."""
        if command not in ALLOWED_COMMANDS:
            raise ValueError(f"Unsupported game command: {command}")
        return await self._request(
            "POST",
            f"/api/cmd/{command}",
            json={"payload": payload or {}, "expectedVersion": expected_version},
            headers={"Idempotency-Key": idempotency_key or str(uuid4())},
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        if not self.cookie:
            raise ValueError("A game session cookie is required.")
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.request(
                method, f"{GAME_ORIGIN}{path}", headers=headers, **kwargs
            )
        data = self._json(response)
        if not response.is_success or data.get("ok") is False:
            self._raise(response, data)
        return data

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _raise(response: httpx.Response, data: dict[str, Any]) -> None:
        raise GameAPIError(
            str(data.get("message") or data.get("errorCode") or f"Game API HTTP {response.status_code}"),
            status_code=response.status_code,
            error_code=data.get("errorCode"),
        )
