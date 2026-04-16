"""Тесты HttpTransport — auth, headers, retry, error mapping."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
    SberIdTokens,
)
from custom_components.sberhome.aiosber.exceptions import (
    ApiError,
    AuthError,
    NetworkError,
    RateLimitError,
)
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[HttpTransport, list[httpx.Request], InMemoryTokenStore]:
    """Helper: HttpTransport с MockTransport + готовым AuthManager."""
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="TOK", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    return HttpTransport(http=http, auth=auth), hits, store


# ---- Headers ----
async def test_request_signs_with_x_auth_jwt_header():
    """Gateway требует X-AUTH-jwt (без Bearer prefix), не стандартный Authorization."""
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport, hits, _ = _build(h)
    async with transport:
        await transport.get("/devices/")

    assert hits[0].headers["x-auth-jwt"] == "TOK"
    # Authorization не должен ставиться — gateway его игнорирует
    assert "authorization" not in hits[0].headers


async def test_request_includes_user_agent_and_trace_id():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport, hits, _ = _build(h)
    async with transport:
        await transport.get("/devices/")

    assert "user-agent" in hits[0].headers
    assert "x-trace-id" in hits[0].headers


async def test_extra_headers_passed_through():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport, hits, _ = _build(h)
    async with transport:
        await transport.get("/devices/", headers={"X-Custom": "v"})

    assert hits[0].headers["x-custom"] == "v"


# ---- URL building ----
async def test_relative_path_prepended_with_base_url():
    def h(req: httpx.Request) -> httpx.Response:
        assert str(req.url).endswith("/gateway/v1/devices/")
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.get("devices/")


async def test_absolute_url_passed_as_is():
    def h(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "https://other.example.com/x"
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.get("https://other.example.com/x")


# ---- Verbs ----
async def test_post_with_json():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["body"] = req.content
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.post("/devices/", json={"x": 1})

    assert captured["method"] == "POST"
    assert b'"x": 1' in captured["body"] or b'"x":1' in captured["body"]


async def test_put_delete_patch_methods():
    methods_seen = []

    def h(req: httpx.Request) -> httpx.Response:
        methods_seen.append(req.method)
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.put("/x")
        await transport.delete("/x")
        await transport.patch("/x")

    assert methods_seen == ["PUT", "DELETE", "PATCH"]


# ---- Retry on 401 ----
async def test_401_triggers_refresh_and_retry():
    """401 → force_refresh() → retry. Финальный 200 — успех."""
    state = {"first_call": True, "refreshed": False}

    def companion(req: httpx.Request) -> httpx.Response:
        state["refreshed"] = True
        return httpx.Response(200, json={"access_token": "NEW_TOK", "expires_in": 3600})

    def gateway(req: httpx.Request) -> httpx.Response:
        if state["first_call"]:
            state["first_call"] = False
            return httpx.Response(401, json={"error": "expired"})
        # После retry — токен должен быть новый
        assert req.headers["x-auth-jwt"] == "NEW_TOK"
        return httpx.Response(200, json={"ok": True})

    def router(req: httpx.Request) -> httpx.Response:
        if "smarthome/token" in req.url.path:
            return companion(req)
        return gateway(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        resp = await transport.get("/devices/")

    assert resp.status_code == 200
    assert state["refreshed"]


async def test_401_after_retry_raises_auth_error():
    """Если и после refresh токен снова 401 — AuthError."""
    def router(req: httpx.Request) -> httpx.Response:
        if "smarthome/token" in req.url.path:
            return httpx.Response(200, json={"access_token": "STILL_BAD", "expires_in": 3600})
        return httpx.Response(401, json={"error": "still bad"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        with pytest.raises(AuthError, match="Unauthorized after refresh"):
            await transport.get("/devices/")


# ---- HTTP status mapping ----
async def test_429_raises_rate_limit_with_retry_after():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429, json={"message": "slow down"}, headers={"Retry-After": "30"}
        )

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(RateLimitError) as exc:
            await transport.get("/devices/")
    assert exc.value.retry_after == 30.0
    assert exc.value.status_code == 429


async def test_429_without_retry_after():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="too many")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(RateLimitError) as exc:
            await transport.get("/devices/")
    assert exc.value.retry_after is None


async def test_404_raises_api_error():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "device not found", "code": "NOT_FOUND"})

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(ApiError) as exc:
            await transport.get("/devices/x")
    assert exc.value.status_code == 404
    assert exc.value.code == "NOT_FOUND"
    assert "device not found" in str(exc.value)


async def test_500_raises_api_error():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(ApiError) as exc:
            await transport.get("/x")
    assert exc.value.status_code == 500


async def test_2xx_returns_response():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(204)  # No Content

    transport, _, _ = _build(h)
    async with transport:
        resp = await transport.delete("/x")
    assert resp.status_code == 204


# ---- Network errors ----
async def test_timeout_mapped_to_network_error():
    def h(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(NetworkError, match="Timeout"):
            await transport.get("/x")


async def test_connect_error_mapped_to_network_error():
    def h(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS down")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(NetworkError, match="Connect failed"):
            await transport.get("/x")


# ---- Lifecycle ----
async def test_aclose_closes_underlying_http():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    await transport.aclose()
    # Повторный запрос должен упасть, потому что клиент закрыт
    with pytest.raises((RuntimeError, NetworkError)):
        await transport.get("/x")
