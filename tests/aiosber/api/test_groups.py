"""Тесты GroupAPI."""

from __future__ import annotations

import json

import httpx

from custom_components.sberhome.aiosber import (
    AttributeValueDto,
    AttrKey,
    SberClient,
)
from custom_components.sberhome.aiosber.api import GroupAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[GroupAPI, list[httpx.Request]]:
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return GroupAPI(transport), hits


# ----- list / get -----
async def test_list_unwraps_result():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/device_groups/")
        return httpx.Response(200, json={"result": [{"id": "g1", "name": "Кухня"}]})

    api, _ = _build(h)
    groups = await api.list()
    assert len(groups) == 1
    assert groups[0].id == "g1"
    assert groups[0].name == "Кухня"


async def test_get_single_group():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"id": "g1", "name": "Кухня"}})

    api, _ = _build(h)
    g = await api.get("g1")
    assert g.id == "g1"
    assert g.name == "Кухня"


async def test_tree_returns_full_structure():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"devices": [], "children": [{"id": "c1"}]}})

    api, _ = _build(h)
    tree = await api.tree()
    assert tree.children is not None


# ----- mutations -----
async def test_create_group_minimal():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(
            200, json={"result": {"id": "new-id", "name": captured["body"]["name"]}}
        )

    api, _ = _build(h)
    g = await api.create("Спальня")
    assert g["id"] == "new-id"
    assert captured["body"] == {"name": "Спальня"}


async def test_create_group_with_parent():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"id": "nested"}})

    api, _ = _build(h)
    await api.create("Подгруппа", parent_id="grp-parent")
    assert captured["body"] == {"name": "Подгруппа", "parent_id": "grp-parent"}


async def test_delete_group():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.method == "DELETE"
        assert req.url.path.endswith("/device_groups/g1")
        return httpx.Response(204)

    api, _ = _build(h)
    await api.delete("g1")


async def test_set_state_sends_desired_state():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["url"] = req.url.path
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    await api.set_state(
        "g1",
        [AttributeValueDto.of_bool(AttrKey.ON_OFF, True)],
        return_group_status=True,
    )
    assert captured["url"].endswith("/device_groups/g1/state")
    body = captured["body"]
    assert body["return_group_status"] is True
    assert body["desired_state"][0]["bool_value"] is True
    assert "timestamp" in body


async def test_set_state_without_return_status():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    await api.set_state("g1", [AttributeValueDto.of_bool("on_off", False)])
    assert "return_group_status" not in captured["body"]


async def test_rename_group():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.rename("g1", "Гостиная")
    assert captured["body"] == {"name": "Гостиная"}


async def test_move_group_to_parent():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.move("g1", "parent-grp")
    assert captured["body"] == {"parent_id": "parent-grp"}


async def test_set_image():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.set_image("g1", "img-uuid")
    assert captured["body"] == {"image_id": "img-uuid"}


async def test_set_silent():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={})

    api, _ = _build(h)
    await api.set_silent("g1", True)
    assert captured["body"] == {"silent": True}


async def test_sber_client_groups_property():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(h))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="X", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    client = SberClient(transport=transport)

    assert isinstance(client.groups, GroupAPI)
    async with client:
        result = await client.groups.list()
    assert result == []  # empty list of UnionDto
