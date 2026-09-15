"""Сервисный слой SberClient поверх фейкового gateway (httpx.MockTransport).

Проверяет сквозной путь «сервис → API → HttpTransport → HTTP» на ответах в
форме реального Sber Gateway: какие запросы уходят и что оказывается в кэше.
"""

from __future__ import annotations

import json

import httpx
import pytest

from custom_components.sberhome.aiosber import AttributeValueDto, AttrKey, SberClient
from custom_components.sberhome.aiosber.api import (
    GroupAPI,
    IndicatorAPI,
    InventoryAPI,
    PairingAPI,
    ScenarioAPI,
    ScenarioTemplatesAPI,
)
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.exceptions import ProtocolError
from custom_components.sberhome.aiosber.transport import HttpTransport

HOME = {"id": "home-1", "name": "Мой дом", "group_type": "HOME"}
KITCHEN = {
    "id": "room-kitchen",
    "name": "Кухня",
    "group_type": "ROOM",
    "parent_id": "home-1",
    "device_ids": ["lamp-1"],
}
EMPTY_ROOM = {"id": "room-hall", "name": "Прихожая", "group_type": "ROOM", "parent_id": "home-1"}
LAMP = {
    "id": "lamp-1",
    "name": {"name": "Люстра", "defaultName": "Лампа", "names": {}},
    "image_set_type": "bulb_sber",
    "group_ids": ["room-kitchen"],
    "parent_id": "room-kitchen",
    "reported_state": [
        {"key": "online", "type": "BOOL", "bool_value": True},
        {"key": "on_off", "type": "BOOL", "bool_value": True},
        {"key": "light_brightness", "type": "INTEGER", "integer_value": "300"},
    ],
    "desired_state": [],
}


class FakeGateway:
    """Минимальный Sber Gateway: отвечает по методу+пути, пишет журнал запросов."""

    def __init__(self, *, devices_payload=None) -> None:
        self.requests: list[tuple[str, str, dict | None]] = []
        self.devices_payload = (
            devices_payload
            if devices_payload is not None
            else {
                # Мусорные элементы в выдаче не должны ронять refresh.
                "result": [LAMP, "garbage", {"name": "без id"}],
                "pagination": {"offset": 0, "limit": 500},
            }
        )
        self.created_group: dict | None = {"result": {"id": "grp-new", "name": "Вечер"}}

    def handler(self, req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        path = req.url.path.removeprefix("/gateway/v1")
        self.requests.append((req.method, path, body))
        if req.method == "GET" and path == "/device_groups":
            kind = req.url.params["group_type"]
            groups = {"HOME": [HOME], "ROOM": [KITCHEN, EMPTY_ROOM], "GROUP": []}[kind]
            return httpx.Response(200, json={"result": groups})
        if req.method == "GET" and path == "/devices":
            return httpx.Response(200, json=self.devices_payload)
        if req.method == "GET" and path == "/devices/enums":
            return httpx.Response(200, json={"result": {"light_mode": ["white", "colour"]}})
        if req.method == "POST" and path == "/device_groups/":
            return httpx.Response(200, json=self.created_group)
        if req.method == "GET" and path.startswith("/scenario/v2/scenario/"):
            return httpx.Response(200, json={"result": {"id": "sc-1", "name": "Утро"}})
        if req.method == "GET" and path == "/scenario/v2/scenario":
            return httpx.Response(200, json={"result": [{"id": "sc-1", "name": "Утро"}]})
        if req.method == "GET" and path == "/scenario/v2/home/variable/at_home":
            return httpx.Response(
                200, json={"variable": {"name": "at_home", "value": {"bool_value": True}}}
            )
        return httpx.Response(200, json={})


def _client(gateway: FakeGateway) -> SberClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(gateway.handler))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    return SberClient(transport=HttpTransport(http=http, auth=AuthManager(http=http, store=store)))


async def test_refresh_fills_cache_and_skips_garbage_devices():
    gateway = FakeGateway()
    async with _client(gateway) as client:
        await client.refresh()

        assert [d.id for d in client.device_service.list_all()] == ["lamp-1"]
        assert client.state.get_raw_payload("lamp-1") == LAMP
        assert client.state.get_enum_values("light_mode") == ["white", "colour"]

        groups = client.group_service
        assert groups.get("room-kitchen").name == "Кухня"
        assert [d.id for d in groups.devices_in_group("room-kitchen")] == ["lamp-1"]
        assert groups.devices_in_group("room-hall") == []
        assert groups.devices_in_group("missing") == []
        assert client.device_service.last_refresh_degraded is False


async def test_refresh_with_unexpected_devices_shape_keeps_groups():
    gateway = FakeGateway(devices_payload={"result": {"devices": "unavailable"}})
    async with _client(gateway) as client:
        await client.refresh()
        assert client.device_service.list_all() == []
        assert client.group_service.get("room-kitchen") is not None


async def test_device_service_commands_hit_gateway_and_patch_cache():
    gateway = FakeGateway()
    async with _client(gateway) as client:
        await client.refresh()
        svc = client.device_service
        await svc.set_brightness("lamp-1", 700)
        await svc.rename("lamp-1", "Люстра в кухне")
        await svc.move_to_group("lamp-1", None)

        desired = client.state.get_device("lamp-1").desired_state
        assert [(a.key, a.value) for a in desired] == [("light_brightness", 700)]

    writes = [(m, p, b) for m, p, b in gateway.requests if m == "PUT"]
    assert writes[0][1] == "/devices/lamp-1/state"
    assert writes[0][2]["desired_state"] == [
        {"key": "light_brightness", "type": "INTEGER", "integer_value": 700}
    ]
    assert writes[1] == ("PUT", "/devices/lamp-1/name", {"name": "Люстра в кухне"})
    assert writes[2] == ("PUT", "/devices/lamp-1/parent", {"parent_id": None})


async def test_group_service_mutations():
    gateway = FakeGateway()
    async with _client(gateway) as client:
        groups = client.group_service
        created = await groups.create("Вечер", parent_id="home-1")
        await groups.set_state("room-kitchen", [AttributeValueDto.of_bool(AttrKey.ON_OFF, False)])
        await groups.rename("room-kitchen", "Кухня-столовая")
        await groups.delete("grp-new")

    assert created.id == "grp-new"
    calls = [(m, p) for m, p, _ in gateway.requests]
    assert calls == [
        ("POST", "/device_groups/"),
        ("PUT", "/device_groups/room-kitchen/state"),
        ("PUT", "/device_groups/room-kitchen/name"),
        ("DELETE", "/device_groups/grp-new"),
    ]
    assert gateway.requests[0][2] == {"name": "Вечер", "parent_id": "home-1"}


async def test_group_service_create_without_parent_and_unparseable_answer():
    gateway = FakeGateway()
    gateway.created_group = {"result": None}
    async with _client(gateway) as client:
        with pytest.raises(ProtocolError, match="created group"):
            await client.group_service.create("Вечер")
    assert gateway.requests[0][2] == {"name": "Вечер"}


async def test_scenario_service_round_trip():
    gateway = FakeGateway()
    async with _client(gateway) as client:
        svc = client.scenario_service
        assert [s.name for s in await svc.list_all()] == ["Утро"]
        assert (await svc.get("sc-1")).id == "sc-1"
        assert await svc.get_at_home() is True
        await svc.set_at_home(False)
        await svc.delete("sc-1")

    assert gateway.requests[-2] == (
        "PUT",
        "/scenario/v2/home/variable/at_home",
        {"bool_value": False},
    )
    assert gateway.requests[-1][:2] == ("DELETE", "/scenario/v2/scenario/sc-1")


async def test_client_exposes_every_api_domain():
    gateway = FakeGateway()
    async with _client(gateway) as client:
        assert isinstance(client.inventory, InventoryAPI)
        assert isinstance(client.scenario_templates, ScenarioTemplatesAPI)
        assert isinstance(client.pairing, PairingAPI)
        assert isinstance(client.indicator, IndicatorAPI)
        assert isinstance(client.scenarios, ScenarioAPI)
        assert isinstance(client.groups, GroupAPI)
