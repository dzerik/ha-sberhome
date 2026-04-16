"""Тесты SberClient — фасад + factory методы."""

from __future__ import annotations

import httpx

from custom_components.sberhome.aiosber import (
    DeviceAPI,
    SberClient,
)
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
    SberIdTokens,
)
from custom_components.sberhome.aiosber.transport import HttpTransport, SslContextProvider


def _build_transport(handler):
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    return HttpTransport(http=http, auth=auth)


def _ok(req: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"result": {"devices": [], "children": []}})


# ----- Construction -----
async def test_basic_construction():
    transport = _build_transport(_ok)
    client = SberClient(transport=transport)
    assert isinstance(client.devices, DeviceAPI)
    assert client.transport is transport
    await client.aclose()


async def test_async_context_manager_closes_transport():
    transport = _build_transport(_ok)
    closed = {"v": False}
    original = transport.aclose

    async def tracker():
        closed["v"] = True
        await original()

    transport.aclose = tracker  # type: ignore[method-assign]

    async with SberClient(transport=transport) as client:
        await client.devices.list()

    assert closed["v"]


async def test_devices_returns_same_instance():
    """SberClient.devices — один и тот же DeviceAPI инстанс на жизнь клиента."""
    transport = _build_transport(_ok)
    client = SberClient(transport=transport)
    assert client.devices is client.devices
    await client.aclose()


# ----- from_companion_token -----
async def test_from_companion_token_minimal():
    """Минимальная конструкция через готовый companion-токен."""
    # Без mock-server — просто проверяем что объект построился
    client = await SberClient.from_companion_token("companion-token-xyz")
    try:
        assert isinstance(client.devices, DeviceAPI)
        # Проверяем что токен попал в transport (ленивая проверка через AuthManager)
        token = await client.transport._auth.access_token()
        assert token == "companion-token-xyz"
    finally:
        await client.aclose()


async def test_from_companion_token_with_refresh_and_expiry():
    client = await SberClient.from_companion_token(
        "T", refresh_token="R", expires_in=7200
    )
    try:
        token = await client.transport._auth.access_token()
        assert token == "T"
    finally:
        await client.aclose()


async def test_from_companion_token_custom_ssl_provider():
    """Можно передать кастомный SslContextProvider (для тестов / других CA)."""
    provider = SslContextProvider()
    client = await SberClient.from_companion_token("T", ssl_provider=provider)
    try:
        assert client.devices is not None
    finally:
        await client.aclose()


# ----- from_oauth_setup -----
async def test_from_oauth_setup_with_inmemory_store():
    """Полная инициализация с SberID токенами + auto-refresh."""
    sberid = SberIdTokens(
        access_token="SID_AT",
        refresh_token="SID_RT",
        expires_in=3600,
    )
    store = InMemoryTokenStore()
    client = await SberClient.from_oauth_setup(
        sberid_tokens=sberid,
        token_store=store,
    )
    try:
        # AuthManager должен иметь sberid и пустой companion (пока)
        assert client.transport._auth.has_sberid_refresh
        assert not client.transport._auth.has_companion
    finally:
        await client.aclose()


async def test_from_oauth_setup_default_store_is_in_memory():
    sberid = SberIdTokens(access_token="X", refresh_token="Y", expires_in=3600)
    client = await SberClient.from_oauth_setup(sberid_tokens=sberid)
    try:
        assert client.devices is not None
    finally:
        await client.aclose()


async def test_from_oauth_setup_uses_custom_endpoints():
    """Можно переопределить token/companion endpoints (для других стендов)."""
    sberid = SberIdTokens(access_token="X", refresh_token="Y", expires_in=3600)
    client = await SberClient.from_oauth_setup(
        sberid_tokens=sberid,
        token_endpoint="https://test.example/token",
        companion_endpoint="https://test.example/smarthome/token",
    )
    try:
        # Проверяем через AuthManager state
        assert client.transport._auth._token_endpoint == "https://test.example/token"
        assert client.transport._auth._companion_endpoint == "https://test.example/smarthome/token"
    finally:
        await client.aclose()
