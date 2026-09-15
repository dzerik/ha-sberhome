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


# ----- lifecycle: set / persist / clear ------------------------------------


def _rotation_handler(calls: dict[str, int], *, refresh_payload: dict | None = None):
    async def handler(req: httpx.Request) -> httpx.Response:
        if "/oidc/v3/token" in req.url.path:
            calls["refresh"] = calls.get("refresh", 0) + 1
            return httpx.Response(
                200,
                json=refresh_payload
                or {"access_token": "ax-new", "refresh_token": "rx-new", "expires_in": 1800},
            )
        if "smarthome/token" in req.url.path:
            calls["smart"] = calls.get("smart", 0) + 1
            return httpx.Response(200, json={"token": "sht-new", "state": {"status": "OK"}})
        raise AssertionError(f"unexpected {req.url}")

    return handler


async def test_set_persist_clear_lifecycle():
    http = _client(_rotation_handler({}))
    store = InMemoryCsafrontTokenStore()
    mgr = CsafrontAuthManager(http=http, store=store)
    assert not mgr.has_tokens
    assert mgr.smart_home_expires_at is None
    await mgr.persist()  # нечего сохранять
    assert await store.load() is None

    tokens = _initial_tokens()
    mgr.set_tokens(tokens)
    assert mgr.has_tokens
    assert mgr.smart_home_expires_at == tokens.csafront_obtained_at + 1800
    await mgr.persist()
    assert await store.load() is tokens

    await mgr.clear()
    assert not mgr.has_tokens
    assert await store.load() is None
    await http.aclose()


async def test_force_refresh_without_tokens_raises_invalid_grant():
    calls: dict[str, int] = {}
    http = _client(_rotation_handler(calls))
    mgr = CsafrontAuthManager(http=http, store=InMemoryCsafrontTokenStore())
    with pytest.raises(InvalidGrant, match="no tokens to refresh"):
        await mgr.force_refresh()
    assert calls == {}
    await http.aclose()


async def test_force_refresh_skips_when_token_already_rotated():
    calls: dict[str, int] = {}
    http = _client(_rotation_handler(calls))
    mgr = CsafrontAuthManager(
        http=http, store=InMemoryCsafrontTokenStore(), initial=_initial_tokens()
    )
    await mgr.force_refresh("sht-old")
    await mgr.force_refresh("sht-old")  # опоздавший 401 со старым токеном
    assert calls == {"refresh": 1, "smart": 1}
    await http.aclose()


async def test_refresh_without_rotation_keeps_refresh_token_and_ttl():
    """Backend вернул только access_token — прежние refresh_token и TTL сохраняются."""
    http = _client(_rotation_handler({}, refresh_payload={"access_token": "ax-new"}))
    store = InMemoryCsafrontTokenStore()
    mgr = CsafrontAuthManager(
        http=http, store=store, initial=_initial_tokens(expires_in=900, age_s=1200)
    )
    assert await mgr.access_token() == "sht-new"
    saved = await store.load()
    assert saved is not None
    assert saved.csafront_access_token == "ax-new"
    assert saved.csafront_refresh_token == "rx-old"
    assert saved.csafront_expires_in == 900
    assert saved.phone == "78001234567"
    await http.aclose()


async def test_failing_refresh_callback_does_not_break_refresh(caplog):
    async def cb(tokens: CsafrontTokens) -> None:
        raise RuntimeError("config entry is gone")

    http = _client(_rotation_handler({}))
    store = InMemoryCsafrontTokenStore()
    mgr = CsafrontAuthManager(
        http=http,
        store=store,
        initial=_initial_tokens(expires_in=10, age_s=120),
        on_tokens_refreshed=cb,
    )
    assert await mgr.access_token() == "sht-new"
    assert (await store.load()).smart_home_token == "sht-new"
    assert "on_tokens_refreshed callback failed" in caplog.text
    await http.aclose()


async def test_set_tokens_lifts_invalid_grant_after_reauth():
    """После отзыва refresh_token запросы не бьют в Sber, пока не пришёл новый SMS-вход."""
    state = {"revoked": True, "refresh": 0}

    async def handler(req: httpx.Request) -> httpx.Response:
        if "/oidc/v3/token" in req.url.path:
            state["refresh"] += 1
            if state["revoked"]:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "ax-new", "expires_in": 1800})
        return httpx.Response(200, json={"token": "sht-new"})

    http = _client(handler)
    mgr = CsafrontAuthManager(
        http=http,
        store=InMemoryCsafrontTokenStore(),
        initial=_initial_tokens(expires_in=10, age_s=120),
    )
    for _ in range(2):
        with pytest.raises(InvalidGrant):
            await mgr.access_token()
    assert state["refresh"] == 1

    state["revoked"] = False
    mgr.set_tokens(_initial_tokens(expires_in=10, age_s=120))
    assert await mgr.access_token() == "sht-new"
    assert state["refresh"] == 2
    await http.aclose()
