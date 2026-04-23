"""Тесты PairingAPI."""

from __future__ import annotations

import json

import httpx

from custom_components.sberhome.aiosber import SberClient
from custom_components.sberhome.aiosber.api import PairingAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.dto import DeviceToPairingBody
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[PairingAPI, list[httpx.Request]]:
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="T", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    return PairingAPI(transport), hits


async def test_start_pairing():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path.endswith("/devices/pairing")
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"session_id": "sess-1"}})

    api, _ = _build(h)
    body = DeviceToPairingBody(image_set_type="bulb_sber", pairing_type="wifi", timeout=120)
    res = await api.start_pairing(body)
    assert res == {"session_id": "sess-1"}
    assert captured["body"]["pairing_type"] == "wifi"


async def test_get_wifi_credentials():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/credentials/wifi")
        return httpx.Response(200, json={"result": {"ssid": "SberSetup", "password": "tmp123"}})

    api, _ = _build(h)
    creds = await api.get_wifi_credentials()
    assert creds["ssid"] == "SberSetup"


async def test_list_matter_categories():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/categories/matter")
        return httpx.Response(200, json={"result": [{"id": "light"}, {"id": "lock"}]})

    api, _ = _build(h)
    cats = await api.list_matter_categories()
    assert len(cats) == 2


async def test_matter_attestation():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"result": {"verified": True}})

    api, _ = _build(h)
    res = await api.matter_attestation({"dac": "..."})
    assert res["verified"] is True


async def test_matter_request_noc():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"noc": "cert..."}})

    api, _ = _build(h)
    res = await api.matter_request_noc({"csr": "..."})
    assert "noc" in res


async def test_matter_complete():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": {"node_id": 12345}})

    api, _ = _build(h)
    res = await api.matter_complete({"fabric_id": "f"})
    assert res["node_id"] == 12345


async def test_matter_connect_controller():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/matter/connect/controller")
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    await api.matter_connect_controller({})


async def test_matter_connect_device():
    def h(req: httpx.Request) -> httpx.Response:
        assert req.url.path.endswith("/devices/matter/connect/device")
        return httpx.Response(200, json={"result": {}})

    api, _ = _build(h)
    await api.matter_connect_device({})


async def test_sber_client_pairing_property():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(h))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="X", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(http=http, auth=auth)
    client = SberClient(transport=transport)
    assert isinstance(client.pairing, PairingAPI)
    async with client:
        await client.pairing.list_matter_categories()
