"""Тесты CsafrontAuthManager — refresh path + persist."""

from __future__ import annotations

import time

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import (
    CsafrontAuthManager,
    CsafrontTokens,
    InMemoryCsafrontTokenStore,
)
from custom_components.sberhome.aiosber.exceptions import InvalidGrant


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _initial_tokens(*, expires_in: int = 1800, age_s: int = 0) -> CsafrontTokens:
    now = time.time() - age_s
    return CsafrontTokens(
        csafront_access_token="ax-old",
        csafront_refresh_token="rx-old",
        smart_home_token="sht-old",
        client_uuid="cu-1",
        csafront_expires_in=expires_in,
        csafront_obtained_at=now,
        smart_home_obtained_at=now,
        phone="78001234567",
    )


# ----- access_token: happy path -------------------------------------------


async def test_access_token_returns_cached_when_not_expired():
    async def handler(req):
        raise AssertionError("should not hit network when token live")

    http = _client(handler)
    store = InMemoryCsafrontTokenStore()
    mgr = CsafrontAuthManager(http=http, store=store, initial=_initial_tokens())
    token = await mgr.access_token()
    assert token == "sht-old"
    await http.aclose()


async def test_access_token_refreshes_when_expired():
    """Просроченный access → refresh CSAFront + новый SmartHomeToken."""
    state = {"step": "refresh"}

    async def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if "/oidc/v3/token" in path:
            assert state["step"] == "refresh"
            state["step"] = "smart"
            return httpx.Response(
                200,
                json={
                    "access_token": "ax-new",
                    "refresh_token": "rx-new",
                    "expires_in": 1800,
                },
            )
        if "smarthome/token" in path:
            assert state["step"] == "smart"
            assert req.headers["Authorization"] == "Bearer ax-new"
            return httpx.Response(200, json={"token": "sht-new"})
        raise AssertionError(f"unexpected url {path}")

    http = _client(handler)
    store = InMemoryCsafrontTokenStore()
    # tokens expired (age > expires_in)
    mgr = CsafrontAuthManager(
        http=http, store=store, initial=_initial_tokens(expires_in=10, age_s=120)
    )
    token = await mgr.access_token()
    assert token == "sht-new"
    # rotated tokens persisted
    saved = await store.load()
    assert saved is not None
    assert saved.csafront_refresh_token == "rx-new"
    assert saved.smart_home_token == "sht-new"
    # client_uuid preserved across rotation
    assert saved.client_uuid == "cu-1"
    await http.aclose()


async def test_force_refresh_unconditionally():
    """force_refresh() обновляет даже когда токен по TTL ещё жив."""
    calls = {"n": 0}

    async def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if "/oidc/v3/token" in req.url.path:
            return httpx.Response(
                200,
                json={"access_token": "ax-new", "refresh_token": "rx-new", "expires_in": 1800},
            )
        if "smarthome/token" in req.url.path:
            return httpx.Response(200, json={"token": "sht-new"})
        raise AssertionError(f"unexpected {req.url}")

    http = _client(handler)
    store = InMemoryCsafrontTokenStore()
    mgr = CsafrontAuthManager(http=http, store=store, initial=_initial_tokens())
    await mgr.force_refresh()
    # token + smart_home calls
    assert calls["n"] == 2
    assert (await store.load()).smart_home_token == "sht-new"
    await http.aclose()


# ----- error path ---------------------------------------------------------


async def test_refresh_invalid_grant_propagates():
    """Если refresh_token уже отозван — InvalidGrant пробрасывается caller'у."""

    async def handler(req: httpx.Request) -> httpx.Response:
        if "/oidc/v3/token" in req.url.path:
            return httpx.Response(400, text="invalid_grant")
        raise AssertionError("smart_home should not be called")

    http = _client(handler)
    store = InMemoryCsafrontTokenStore()
    mgr = CsafrontAuthManager(
        http=http, store=store, initial=_initial_tokens(expires_in=10, age_s=120)
    )
    with pytest.raises(InvalidGrant):
        await mgr.access_token()
    await http.aclose()


async def test_access_token_without_initial_raises_invalid_grant():
    async def handler(req):
        raise AssertionError("no http expected")

    http = _client(handler)
    store = InMemoryCsafrontTokenStore()
    mgr = CsafrontAuthManager(http=http, store=store)
    with pytest.raises(InvalidGrant):
        await mgr.access_token()
    await http.aclose()


# ----- persist + callback -------------------------------------------------


async def test_on_tokens_refreshed_callback_invoked():
    """После успешной ротации callback вызывается с новыми tokens."""
    captured: list[CsafrontTokens] = []

    async def cb(tokens: CsafrontTokens) -> None:
        captured.append(tokens)

    async def handler(req: httpx.Request) -> httpx.Response:
        if "/oidc/v3/token" in req.url.path:
            return httpx.Response(
                200,
                json={"access_token": "ax-new", "refresh_token": "rx-new", "expires_in": 1800},
            )
        if "smarthome/token" in req.url.path:
            return httpx.Response(200, json={"token": "sht-new"})
        raise AssertionError

    http = _client(handler)
    mgr = CsafrontAuthManager(
        http=http,
        store=InMemoryCsafrontTokenStore(),
        initial=_initial_tokens(expires_in=10, age_s=120),
        on_tokens_refreshed=cb,
    )
    await mgr.access_token()
    assert len(captured) == 1
    assert captured[0].smart_home_token == "sht-new"
    await http.aclose()


async def test_load_from_store_when_no_initial():
    """access_token() подхватывает токены из store при первом вызове."""
    saved = _initial_tokens()
    store = InMemoryCsafrontTokenStore(initial=saved)

    async def handler(req):
        raise AssertionError("token is fresh, no HTTP expected")

    http = _client(handler)
    mgr = CsafrontAuthManager(http=http, store=store)  # initial=None
    token = await mgr.access_token()
    assert token == "sht-old"
    await http.aclose()
