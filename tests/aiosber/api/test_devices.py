"""Тесты DeviceAPI."""

from __future__ import annotations

import json
import re

import httpx
import pytest

from custom_components.sberhome.aiosber import (
    AttributeValueDto,
    AttrKey,
    DeviceAPI,
    DeviceDto,
    SberClient,
)
from custom_components.sberhome.aiosber.api.devices import (
    flatten_device_tree,
)
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.exceptions import ApiError, ProtocolError
from custom_components.sberhome.aiosber.transport import HttpTransport


def _device(id_: str, name: str, image: str = "bulb_sber") -> dict:
    return {
        "id": id_,
        "name": name,
        "image_set_type": image,
        "device_type_name": image,
        "reported_state": [
            {"key": "online", "type": "BOOL", "bool_value": True},
            {"key": "on_off", "type": "BOOL", "bool_value": False},
        ],
        "desired_state": [],
    }


def _build(handler) -> tuple[DeviceAPI, list[httpx.Request]]:
    """Build DeviceAPI with a MockTransport handler. Returns (api, requests)."""
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="TOK", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return DeviceAPI(transport), hits


# ----- flatten_device_tree -----
def test_flatten_empty_tree():
    assert flatten_device_tree({}) == []
    assert flatten_device_tree({"devices": [], "children": []}) == []


def test_flatten_flat_tree():
    tree = {"devices": [{"id": "a"}, {"id": "b"}], "children": []}
    result = flatten_device_tree(tree)
    assert [d["id"] for d in result] == ["a", "b"]


def test_flatten_nested_tree():
    tree = {
        "devices": [{"id": "root1"}],
        "children": [
            {
                "devices": [{"id": "g1d1"}, {"id": "g1d2"}],
                "children": [
                    {"devices": [{"id": "g1g2d1"}], "children": []}
                ],
            },
            {"devices": [{"id": "g2d1"}], "children": []},
        ],
    }
    result = flatten_device_tree(tree)
    ids = sorted([d["id"] for d in result])
    assert ids == ["g1d1", "g1d2", "g1g2d1", "g2d1", "root1"]


def test_flatten_handles_missing_keys():
    """devices/children могут отсутствовать или быть null."""
    assert flatten_device_tree({"devices": None, "children": None}) == []
    assert flatten_device_tree({"devices": [{"id": "x"}]}) == [{"id": "x"}]


# ----- list() -----
async def test_list_returns_devices_from_tree():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "result": {
                    "devices": [_device("1", "Lamp")],
                    "children": [
                        {
                            "devices": [_device("2", "Strip", "led_strip")],
                            "children": [],
                        }
                    ],
                }
            },
        )

    api, hits = _build(h)
    devices = await api.list()
    assert len(devices) == 2
    assert all(isinstance(d, DeviceDto) for d in devices)
    ids = sorted(d.id for d in devices)
    assert ids == ["1", "2"]
    # Endpoint
    assert hits[0].url.path.endswith("/device_groups/tree")
    assert hits[0].method == "GET"


async def test_list_unwraps_result_envelope():
    """{"result": {...}} обёртка должна разворачиваться."""
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"result": {"devices": [_device("x", "Y")], "children": []}, "code": 0},
        )

    api, _ = _build(h)
    devices = await api.list()
    assert len(devices) == 1
    assert devices[0].id == "x"


async def test_list_empty_tree():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"devices": [], "children": []}})

    api, _ = _build(h)
    assert await api.list() == []


async def test_list_404_raises_api_error():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "not found"})

    api, _ = _build(h)
    with pytest.raises(ApiError) as exc:
        await api.list()
    assert exc.value.status_code == 404


# ----- list_flat() -----
async def test_list_flat_devices_endpoint():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/")
        return httpx.Response(200, json={"result": [_device("a", "A")]})

    api, _ = _build(h)
    devices = await api.list_flat()
    assert len(devices) == 1
    assert devices[0].id == "a"


async def test_list_flat_protocol_error_on_non_list():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"not": "a list"}})

    api, _ = _build(h)
    with pytest.raises(ProtocolError, match="Expected list"):
        await api.list_flat()


# ----- get() -----
async def test_get_single_device():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/abc-123")
        return httpx.Response(200, json={"result": _device("abc-123", "X")})

    api, _ = _build(h)
    device = await api.get("abc-123")
    assert device.id == "abc-123"


async def test_get_protocol_error_on_non_dict():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": ["not", "a", "dict"]})

    api, _ = _build(h)
    with pytest.raises(ProtocolError, match="Expected dict"):
        await api.get("x")


# ----- set_state() -----
async def test_set_state_sends_correct_body():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["url"] = req.url.path
        captured["method"] = req.method
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    await api.set_state(
        "dev-1",
        [
            AttributeValueDto.of_bool(AttrKey.ON_OFF, True),
            AttributeValueDto.of_int(AttrKey.LIGHT_BRIGHTNESS, 500),
        ],
    )

    assert captured["method"] == "PUT"
    assert captured["url"].endswith("/devices/dev-1/state")
    body = captured["body"]
    assert body["device_id"] == "dev-1"
    assert len(body["desired_state"]) == 2
    assert body["desired_state"][0] == {"key": "on_off", "type": "BOOL", "bool_value": True}
    # timestamp — UTC ISO с Z
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z", body["timestamp"])


async def test_set_state_with_explicit_timestamp():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    ts = "2026-04-16T12:00:00.000Z"
    await api.set_state("d", [AttributeValueDto.of_bool("on_off", True)], timestamp=ts)
    assert captured["body"]["timestamp"] == ts


# ----- rename / move -----
async def test_rename():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["url"] = req.url.path
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.rename("dev-1", "Кухня")
    assert captured["url"].endswith("/devices/dev-1/name")
    assert captured["body"] == {"name": "Кухня"}


async def test_move_to_group():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.move("dev-1", "grp-uuid")
    assert captured["body"] == {"parent_id": "grp-uuid"}


async def test_move_to_root():
    """parent_id=None — вынести из группы."""
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.move("dev-1", None)
    # parent_id=None должен сохраниться в JSON как null
    assert captured["body"] == {"parent_id": None}


# ----- enums / discover -----
async def test_enums():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/enums")
        return httpx.Response(200, json={"result": {"hvac_work_mode": ["cool", "heat"]}})

    api, _ = _build(h)
    enums = await api.enums()
    assert enums == {"hvac_work_mode": ["cool", "heat"]}


async def test_discover():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/dev-1/discovery")
        return httpx.Response(200, json={"result": {"sub_devices": []}})

    api, _ = _build(h)
    info = await api.discover("dev-1")
    assert "sub_devices" in info


# ----- Headers signed by HttpTransport -----
async def test_request_carries_authorization():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json={"result": {"devices": [], "children": []}})

    api, _ = _build(h)
    await api.list()
    assert captured["auth"] == "Bearer TOK"


# ----- SberClient integration -----
async def test_sber_client_devices_property():
    """SberClient.devices возвращает DeviceAPI на тот же transport."""
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"devices": [], "children": []}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(h))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="X", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    client = SberClient(transport=transport)

    assert isinstance(client.devices, DeviceAPI)
    assert client.transport is transport

    async with client:
        result = await client.devices.list()
    assert result == []
