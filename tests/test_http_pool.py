import unittest
from unittest.mock import patch

import httpx

from api import http_pool


class HttpPoolTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.clients, self.cookies = [], []
        real_client = httpx.AsyncClient

        def handle(request):
            self.cookies.append(request.headers.get("Cookie"))
            return httpx.Response(200, json={"ok": True}, headers={"Set-Cookie": "test_session=value; Path=/"})

        def create(**kwargs):
            client = real_client(transport=httpx.MockTransport(handle), **kwargs)
            self.clients.append(client)
            return client

        p = patch.object(http_pool.httpx, "AsyncClient", side_effect=create)
        p.start(); self.addCleanup(p.stop)

    async def get(self, service="game"):
        return await http_pool.request(service, "GET", "https://game.test/state", timeout=5)

    async def test_reuses_one_client_per_service_and_separates_cookies(self):
        async with http_pool.connection_scope():
            for _ in range(5):
                await self.get()
            await self.get("database")
            self.assertEqual(len(self.clients), 2)
            self.assertTrue(all(not c.is_closed for c in self.clients))
        self.assertTrue(all(c.is_closed for c in self.clients))
        self.assertIsNone(self.cookies[0])
        self.assertEqual(self.cookies[1], "test_session=value")
        self.assertIsNone(self.cookies[-1])

    async def test_new_tick_and_nested_scopes_never_reuse_account_cookies(self):
        async with http_pool.connection_scope():
            await self.get()
            async with http_pool.connection_scope():
                await self.get()
            await self.get()
        async with http_pool.connection_scope():
            await self.get()
        self.assertEqual(len(self.clients), 3)
        self.assertEqual(self.cookies, [None, None, "test_session=value", None])
        self.assertTrue(all(c.is_closed for c in self.clients))

    async def test_scope_closes_clients_after_failure_and_does_not_retry(self):
        async with http_pool.connection_scope():
            with self.assertRaises(RuntimeError):
                async with http_pool.connection_scope():
                    await self.get()
                    raise RuntimeError("failed mutation")
            self.assertTrue(self.clients[0].is_closed)
        self.assertEqual(len(self.cookies), 1)
        self.assertIsNone(http_pool._scope.get())

    async def test_requests_outside_tick_keep_short_lived_behavior(self):
        await self.get()
        await self.get()
        self.assertEqual(len(self.clients), 2)
        self.assertTrue(all(c.is_closed for c in self.clients))
        self.assertEqual(self.cookies, [None, None])
