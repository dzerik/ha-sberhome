"""Тесты ScenarioAPI."""

from __future__ import annotations

import json

import httpx

from custom_components.sberhome.aiosber import SberClient
from custom_components.sberhome.aiosber.api import ScenarioAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[ScenarioAPI, list[httpx.Request]]:
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return ScenarioAPI(transport), hits


async def test_list_scenarios():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/scenario/v2/scenario")
        return httpx.Response(200, json={"result": [{"id": "s1", "name": "Утро"}]})

    api, _ = _build(h)
    items = await api.list()
    assert items[0].name == "Утро"


async def test_get_scenario_by_id():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"id": "s1", "name": "Вечер"}})

    api, _ = _build(h)
    s = await api.get("s1")
    assert s.name == "Вечер"


async def test_list_system_scenarios():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/scenario/v2/system-scenario")
        return httpx.Response(200, json={"result": [{"id": "sys1"}]})

    api, _ = _build(h)
    items = await api.list_system()
    assert len(items) == 1


async def test_list_widgets():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": []})

    api, _ = _build(h)
    assert await api.list_widgets() == []


async def test_create_scenario_passes_body():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"id": "new"}})

    api, _ = _build(h)
    body = {"name": "Test", "trigger": {"type": "time", "at": "08:00"}}
    result = await api.create(body)
    assert result == {"id": "new"}
    assert captured["body"] == body


async def test_update_scenario():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        assert req.method == "PUT"
        captured["url"] = req.url.path
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"id": "s1"}})

    api, _ = _build(h)
    await api.update("s1", {"name": "Updated"})
    assert captured["url"].endswith("/scenario/v2/scenario/s1")


async def test_delete_scenario():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.method == "DELETE"
        return httpx.Response(204)

    api, _ = _build(h)
    await api.delete("s1")


async def test_execute_command():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"ok": True}})

    api, _ = _build(h)
    cmd = {"action": "turn_on", "device_id": "d1"}
    res = await api.execute_command(cmd)
    assert res == {"ok": True}
    assert captured["body"] == cmd


async def test_fire_event():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"triggered": True}})

    api, _ = _build(h)
    res = await api.fire_event({"name": "i_am_home"})
    assert res["triggered"] is True


async def test_set_requires():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.set_requires({"requires": ["geo"]})
    assert captured["body"] == {"requires": ["geo"]}


async def test_at_home_get():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/scenario/v2/home/variable/at_home")
        return httpx.Response(200, json={"result": {"at_home": True}})

    api, _ = _build(h)
    assert await api.get_at_home() is True


async def test_at_home_get_default_false():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    assert await api.get_at_home() is False


async def test_at_home_set():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.set_at_home(False)
    assert captured["body"] == {"at_home": False}


async def test_get_form():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"sections": []}})

    api, _ = _build(h)
    form = await api.get_form()
    assert "sections" in form


async def test_sber_client_scenarios_property():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(h))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="X", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    client = SberClient(transport=transport)
    assert isinstance(client.scenarios, ScenarioAPI)
    async with client:
        await client.scenarios.list()
