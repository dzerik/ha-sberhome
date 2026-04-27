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


# ---------------------------------------------------------------------------
# run — programmatic execute scenario by id
# ---------------------------------------------------------------------------


async def test_run_scenario_posts_to_run_endpoint():
    """POST /scenario/v2/scenario/{id}/run с body {is_active: true}.

    Programmatic-run endpoint (decompiled `runScenario`) — то же что
    кнопка «Запустить действие» в мобильном приложении.
    """
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["path"] = req.url.path
        captured["method"] = req.method
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    result = await api.run("sc-42")
    assert captured["method"] == "POST"
    assert captured["path"].endswith("/scenario/v2/scenario/sc-42/run")
    assert captured["body"] == {"is_active": True}
    assert isinstance(result, dict)


async def test_run_scenario_handles_empty_response():
    """Sber может вернуть пустое тело — не должны падать."""

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    api, _ = _build(h)
    result = await api.run("sc-1")
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# history (event log) — для voice-intents
# ---------------------------------------------------------------------------


async def test_history_returns_events_dto():
    """Sber отвечает {events: [...], pagination: {...}} БЕЗ result-обёртки."""
    payload = {
        "events": [
            {
                "id": "e1",
                "event_time": "2026-04-27T12:44:49.430277Z",
                "object_id": "sc-1",
                "object_type": "SCENARIO",
                "name": "Маркер один",
                "type": "SUCCESS",
            },
            {
                "id": "e2",
                "event_time": "2026-04-27T12:44:18.922428Z",
                "object_id": "sc-1",
                "object_type": "SCENARIO",
                "name": "Маркер один",
                "type": "SUCCESS",
            },
        ],
        "pagination": {"limit": "5", "offset": "0", "has_next": True},
    }

    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/scenario/v2/event")
        # query params попадают в URL
        assert req.url.params["home_id"] == "home-1"
        assert req.url.params["pagination.offset"] == "0"
        assert req.url.params["pagination.limit"] == "5"
        return httpx.Response(200, json=payload)

    api, _ = _build(h)
    events = await api.history("home-1", limit=5)
    assert len(events) == 2
    assert events[0].name == "Маркер один"
    assert events[0].object_id == "sc-1"
    assert events[0].type == "SUCCESS"


async def test_history_handles_result_wrapper():
    """Backward-compat: если Sber начнёт оборачивать в result."""

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"events": [{"id": "x", "name": "Y"}]}})

    api, _ = _build(h)
    events = await api.history("home-1")
    assert events[0].name == "Y"


async def test_history_empty_events():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"events": [], "pagination": {}})

    api, _ = _build(h)
    assert await api.history("home-1") == []


async def test_history_garbled_payload_returns_empty():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"oops": "no events here"})

    api, _ = _build(h)
    assert await api.history("home-1") == []


async def test_history_filters_non_dict_event_items():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"events": [{"id": "ok"}, "garbage", 42, None]},
        )

    api, _ = _build(h)
    events = await api.history("home-1")
    assert len(events) == 1
    assert events[0].id == "ok"
