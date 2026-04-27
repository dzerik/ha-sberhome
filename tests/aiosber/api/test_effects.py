"""Тесты LightEffectsAPI — `/light/effects`."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.api import LightEffectsAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> LightEffectsAPI:
    def wrapper(req: httpx.Request) -> httpx.Response:
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return LightEffectsAPI(transport)


@pytest.mark.asyncio
async def test_list_returns_array_payload():
    payload = [
        {"id": "fx-aurora", "name": "Aurora", "category": "nature"},
        {"id": "fx-disco", "name": "Disco", "category": "party"},
    ]

    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/light/effects")
        return httpx.Response(200, json={"result": payload})

    api = _build(h)
    assert await api.list() == payload


@pytest.mark.asyncio
async def test_list_returns_dict_with_effects_field():
    """Sber иногда отдаёт {effects: [...], categories: [...]}."""
    effects = [{"id": "fx-1", "name": "One"}]

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"result": {"effects": effects, "categories": ["mood"]}},
        )

    api = _build(h)
    assert await api.list() == effects


@pytest.mark.asyncio
async def test_list_returns_empty_on_garbled_payload():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": None})

    api = _build(h)
    assert await api.list() == []
