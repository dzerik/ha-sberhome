"""Тесты IndicatorAPI."""

from __future__ import annotations

import json

import httpx

from custom_components.sberhome.aiosber import SberClient
from custom_components.sberhome.aiosber.api import IndicatorAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.dto import IndicatorColor
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[IndicatorAPI, list[httpx.Request]]:
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return IndicatorAPI(transport), hits


def _sample_indicator_payload() -> dict:
    return {
        "default_colors": [
            {"id": "online-default", "hue": 120, "saturation": 100, "brightness": 50},
        ],
        "current_colors": [
            {"id": "online-1", "hue": 200, "saturation": 80, "brightness": 70},
        ],
    }


async def test_get_returns_indicator_colors_dto():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/indicator/values")
        return httpx.Response(200, json={"result": _sample_indicator_payload()})

    api, _ = _build(h)
    colors = await api.get()
    assert len(colors.default_colors) == 1
    assert colors.default_colors[0].hue == 120
    assert len(colors.current_colors) == 1
    assert colors.current_colors[0].brightness == 70


async def test_get_raw_returns_dict():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": _sample_indicator_payload()})

    api, _ = _build(h)
    raw = await api.get_raw()
    assert "default_colors" in raw
    assert raw["current_colors"][0]["id"] == "online-1"


async def test_set_sends_indicator_color():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        assert req.method == "PUT"
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.set(IndicatorColor(id="led-x", hue=300, saturation=70, brightness=80))
    assert captured["body"] == {
        "indicator_color": {
            "id": "led-x",
            "hue": 300,
            "saturation": 70,
            "brightness": 80,
        }
    }


async def test_sber_client_indicator_property():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": _sample_indicator_payload()})

    http = httpx.AsyncClient(transport=httpx.MockTransport(h))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="X", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    client = SberClient(transport=transport)
    assert isinstance(client.indicator, IndicatorAPI)
    async with client:
        await client.indicator.get()
