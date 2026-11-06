"""Lazy HTTP keep-alive pools scoped to one automation tick, never global sessions."""

from contextlib import AsyncExitStack, asynccontextmanager
from contextvars import ContextVar

import httpx


_scope: ContextVar[tuple[AsyncExitStack, dict] | None] = ContextVar("http_scope", default=None)


@asynccontextmanager
async def connection_scope():
    # Always isolate account cookies/connections, including nested/manual runs.
    async with AsyncExitStack() as stack:
        token = _scope.set((stack, {}))
        try:
            yield
        finally:
            _scope.reset(token)


async def request(service: str, method: str, url: str, *, timeout: float, **kwargs) -> httpx.Response:
    scope = _scope.get()
    if scope is None:
        async with httpx.AsyncClient(timeout=timeout) as client:
            return await client.request(method, url, **kwargs)
    stack, clients = scope
    if service not in clients:
        clients[service] = await stack.enter_async_context(httpx.AsyncClient(timeout=timeout))
    # Game and database never share a cookie jar. Headers remain per request.
    return await clients[service].request(method, url, timeout=timeout, **kwargs)
