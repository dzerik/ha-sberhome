"""Тесты InventoryAPI — `/inventory/*` endpoints (OTA, tokens, OTP)."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.api import InventoryAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[InventoryAPI, list[httpx.Request]]:
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return InventoryAPI(transport), hits


@pytest.mark.asyncio
async def test_list_ota_upgrades_returns_dict():
    payload = {
        "device-1": {
            "available_version": "26.2.0",
            "current_version": "26.1.4",
            "release_notes": "Fix Zigbee pairing.",
            "severity": "recommended",
        },
        "device-2": {"available_version": "1.0.5"},
    }

    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/inventory/ota-upgrades")
        return httpx.Response(200, json={"result": payload})

    api, hits = _build(h)
    result = await api.list_ota_upgrades()
    assert result == payload
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_list_ota_upgrades_no_result_wrapper():
    """Backward-compat: endpoint иногда отдаёт сразу dict без result."""
    payload = {"device-x": {"available_version": "2.0.0"}}

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    api, _ = _build(h)
    assert await api.list_ota_upgrades() == payload


@pytest.mark.asyncio
async def test_list_ota_upgrades_empty_result():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    assert await api.list_ota_upgrades() == {}


@pytest.mark.asyncio
async def test_list_ota_upgrades_garbled_payload_returns_empty():
    """Защита от non-dict payload (Sber иногда отдаёт null при no-data)."""

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": None})

    api, _ = _build(h)
    assert await api.list_ota_upgrades() == {}


@pytest.mark.asyncio
async def test_list_tokens_passes_through():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/inventory/tokens")
        return httpx.Response(200, json={"result": {"binding": "abc"}})

    api, _ = _build(h)
    assert await api.list_tokens() == {"binding": "abc"}


@pytest.mark.asyncio
async def test_get_otp_passes_through():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/inventory/otp")
        return httpx.Response(200, json={"result": {"otp": "123456", "ttl": 60}})

    api, _ = _build(h)
    assert await api.get_otp() == {"otp": "123456", "ttl": 60}
