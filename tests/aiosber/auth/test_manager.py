"""Тесты AuthManager — refresh logic, asyncio.Lock, persistence."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
    SberIdTokens,
)
from custom_components.sberhome.aiosber.exceptions import InvalidGrant


def _client_recording(routes: dict[str, callable]) -> tuple[httpx.AsyncClient, list]:
    """Create AsyncClient routing by request path. Returns (client, hits)."""
    hits: list[tuple[str, httpx.Request]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        hits.append((path, req))
        for prefix, fn in routes.items():
            if path.endswith(prefix):
                return fn(req)
        return httpx.Response(404, text=f"unrouted: {path}")

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), hits


# ---- access_token: cached ----
async def test_access_token_returns_cached_when_fresh():
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="CACHED", expires_in=3600))
    client, _ = _client_recording({})
    async with client as http:
        mgr = AuthManager(http=http, store=store)
        token = await mgr.access_token()
    assert token == "CACHED"


async def test_access_token_loads_from_store_once():
    """access_token() считывает store при первом вызове (lazy load)."""
    initial = CompanionTokens(access_token="FROM_STORE", expires_in=3600)
    store = InMemoryTokenStore(initial=initial)
    client, _ = _client_recording({})
    async with client as http:
        mgr = AuthManager(http=http, store=store)
        # До вызова access_token — companion ещё не загружен
        assert not mgr.has_companion
        token = await mgr.access_token()
        assert token == "FROM_STORE"
        assert mgr.has_companion


# ---- access_token: refresh via SberID exchange ----
async def test_access_token_exchanges_companion_when_missing():
    """Если в store пусто, но есть SberID — обменять и сохранить."""
    store = InMemoryTokenStore()
    sberid = SberIdTokens(access_token="SID_AT", refresh_token="SID_RT", expires_in=3600)

    def companion_handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer SID_AT"
        return httpx.Response(200, json={"access_token": "NEW_COMP", "expires_in": 3600})

    client, hits = _client_recording({"/smarthome/token": companion_handler})

    async with client as http:
        mgr = AuthManager(http=http, store=store, sberid_tokens=sberid)
        token = await mgr.access_token()

    assert token == "NEW_COMP"
    saved = await store.load()
    assert saved is not None and saved.access_token == "NEW_COMP"


async def test_access_token_refreshes_expired_companion():
    """Если companion истёк — refresh."""
    expired = CompanionTokens(access_token="OLD", expires_in=10, obtained_at=time.time() - 1000)
    store = InMemoryTokenStore(initial=expired)
    sberid = SberIdTokens(access_token="SID_AT", refresh_token="SID_RT", expires_in=3600)

    def companion_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "FRESH", "expires_in": 3600})

    client, _ = _client_recording({"/smarthome/token": companion_handler})

    async with client as http:
        mgr = AuthManager(http=http, store=store, sberid_tokens=sberid)
        token = await mgr.access_token()

    assert token == "FRESH"


async def test_refreshes_sberid_when_expired_then_companion():
    """Истёк и SberID, и companion — сначала refresh SberID, потом companion."""
    sberid_old = SberIdTokens(
        access_token="OLD_SID", refresh_token="RT", expires_in=10, obtained_at=time.time() - 1000
    )

    def token_handler(req: httpx.Request) -> httpx.Response:
        body = req.content.decode()
        assert "grant_type=refresh_token" in body
        assert "refresh_token=RT" in body
        return httpx.Response(
            200,
            json={
                "access_token": "NEW_SID",
                "refresh_token": "NEW_RT",
                "expires_in": 3600,
            },
        )

    def companion_handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["authorization"] == "Bearer NEW_SID"
        return httpx.Response(200, json={"access_token": "COMP", "expires_in": 3600})

    client, hits = _client_recording({
        "/v3/token": token_handler,
        "/smarthome/token": companion_handler,
    })
    store = InMemoryTokenStore()
    async with client as http:
        mgr = AuthManager(http=http, store=store, sberid_tokens=sberid_old)
        token = await mgr.access_token()

    assert token == "COMP"
    paths = [h[0] for h in hits]
    assert any("v3/token" in p for p in paths)
    assert any("smarthome/token" in p for p in paths)


# ---- access_token: invalid_grant → InvalidGrant ----
async def test_no_sberid_raises_invalid_grant():
    store = InMemoryTokenStore()
    client, _ = _client_recording({})
    async with client as http:
        mgr = AuthManager(http=http, store=store)  # без sberid_tokens
        with pytest.raises(InvalidGrant):
            await mgr.access_token()


async def test_expired_sberid_no_refresh_token_raises():
    expired = SberIdTokens(
        access_token="X", refresh_token=None, expires_in=10, obtained_at=time.time() - 1000
    )
    store = InMemoryTokenStore()
    client, _ = _client_recording({})
    async with client as http:
        mgr = AuthManager(http=http, store=store, sberid_tokens=expired)
        with pytest.raises(InvalidGrant, match="no refresh_token"):
            await mgr.access_token()


# ---- Concurrency: asyncio.Lock ----
async def test_concurrent_access_serializes_one_refresh():
    """5 одновременных access_token() — companion endpoint должен быть вызван один раз."""
    store = InMemoryTokenStore()
    sberid = SberIdTokens(access_token="SID", expires_in=3600, refresh_token="RT")
    companion_calls = 0

    def companion_handler(req: httpx.Request) -> httpx.Response:
        nonlocal companion_calls
        companion_calls += 1
        return httpx.Response(200, json={"access_token": "COMP", "expires_in": 3600})

    client, _ = _client_recording({"/smarthome/token": companion_handler})

    async with client as http:
        mgr = AuthManager(http=http, store=store, sberid_tokens=sberid)
        results = await asyncio.gather(*[mgr.access_token() for _ in range(5)])

    assert all(r == "COMP" for r in results)
    assert companion_calls == 1


# ---- force_refresh ----
async def test_force_refresh_renews_even_when_valid():
    fresh = CompanionTokens(access_token="STALE", expires_in=3600)
    store = InMemoryTokenStore(initial=fresh)
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)

    def companion_handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": "RENEWED", "expires_in": 3600})

    client, _ = _client_recording({"/smarthome/token": companion_handler})

    async with client as http:
        mgr = AuthManager(http=http, store=store, sberid_tokens=sberid)
        # Первый access — кешированный
        assert (await mgr.access_token()) == "STALE"
        # force_refresh даже валидного
        await mgr.force_refresh()
        assert (await mgr.access_token()) == "RENEWED"


# ---- clear ----
async def test_clear_removes_everything():
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="X", expires_in=3600))
    sberid = SberIdTokens(access_token="Y", expires_in=3600)
    client, _ = _client_recording({})
    async with client as http:
        mgr = AuthManager(http=http, store=store, sberid_tokens=sberid)
        await mgr.access_token()  # подгружает
        await mgr.clear()
        assert not mgr.has_companion
        assert not mgr.has_sberid_refresh
        assert (await store.load()) is None
