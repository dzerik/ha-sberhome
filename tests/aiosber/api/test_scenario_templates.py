"""Тесты ScenarioTemplatesAPI — `/scenario-templates/*`."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.api import ScenarioTemplatesAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[ScenarioTemplatesAPI, list[httpx.Request]]:
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return ScenarioTemplatesAPI(transport), hits


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,path_suffix",
    [
        ("list_short", "/scenario-templates/short"),
        ("list_device", "/scenario-templates/device"),
        ("list_group", "/scenario-templates/group"),
        ("list_rooms", "/scenario-templates/rooms"),
        ("list_screen", "/scenario-templates/screen/"),
        ("list_hidden", "/scenario-templates/hide"),
    ],
)
async def test_each_method_hits_its_endpoint(method, path_suffix):
    items = [{"id": "t-1", "name": "Template 1"}]

    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith(path_suffix), req.url.path
        return httpx.Response(200, json={"result": items})

    api, hits = _build(h)
    result = await getattr(api, method)()
    assert result == items
    assert len(hits) == 1


@pytest.mark.asyncio
async def test_list_short_extracts_templates_field():
    """Возможный shape: `{templates: [...]}`."""

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"result": {"templates": [{"id": "x"}], "version": 2}}
        )

    api, _ = _build(h)
    assert await api.list_short() == [{"id": "x"}]


@pytest.mark.asyncio
async def test_list_short_returns_empty_when_payload_unrecognised():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": "broken"})

    api, _ = _build(h)
    assert await api.list_short() == []


@pytest.mark.asyncio
async def test_list_short_filters_non_dict_items():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": [{"id": "a"}, "junk", 42]})

    api, _ = _build(h)
    assert await api.list_short() == [{"id": "a"}]
