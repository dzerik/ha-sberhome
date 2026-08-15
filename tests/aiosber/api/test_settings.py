"""Тесты StarosSettingsAPI — канал настроек колонок (companion /v18/*)."""

from __future__ import annotations

import json

import httpx
import pytest

from custom_components.sberhome.aiosber.api.settings import StarosSettingsAPI
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.const import COMPANION_BASE_URL
from custom_components.sberhome.aiosber.dto.settings import (
    SettingNodeDto,
    SettingScreenDto,
    StarosDeviceDto,
)
from custom_components.sberhome.aiosber.transport import HttpTransport

PRODUCT = "sberboom-r2"
SERIAL = "31465833500100000b343349"


def _build(handler) -> tuple[StarosSettingsAPI, list[httpx.Request]]:
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="TOK", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    transport = HttpTransport(
        http=http,
        auth=auth,
        base_url=COMPANION_BASE_URL,
        auth_header_name="Authorization",
        auth_header_prefix="Bearer ",
    )
    return StarosSettingsAPI(transport), hits


def _json(req: httpx.Request) -> dict:
    body = req.content.decode() or "{}"
    return json.loads(body)


# ----- Транспорт: Bearer, без X-AUTH-jwt -----
@pytest.mark.asyncio
async def test_uses_bearer_not_xauth():
    def handler(req):
        return httpx.Response(200, json={"devices": []})

    api, hits = _build(handler)
    await api.list_devices()
    auth = hits[0].headers.get("Authorization")
    assert auth == "Bearer TOK"
    assert "X-AUTH-jwt" not in hits[0].headers


# ----- list_devices -----
@pytest.mark.asyncio
async def test_list_devices():
    def handler(req):
        assert req.url.path == "/v18/devices"
        return httpx.Response(
            200,
            json={
                "state": {"status": 200},
                "devices": [
                    {"deviceId": "d1", "serialNumber": SERIAL, "product": PRODUCT},
                ],
            },
        )

    api, _ = _build(handler)
    devices = await api.list_devices()
    assert len(devices) == 1
    assert isinstance(devices[0], StarosDeviceDto)
    assert devices[0].device_id == "d1"
    assert devices[0].serial_number == SERIAL
    assert devices[0].product == PRODUCT


# ----- get_settings: без screen (сервер отдаёт корневой экран), парсинг узлов -----
@pytest.mark.asyncio
async def test_get_settings_omits_screen_and_parses():
    def handler(req):
        body = _json(req)
        assert req.url.path == "/v18/devices/settings"
        assert body == {"product": PRODUCT, "serialNumber": SERIAL}  # НЕТ screen:null
        return httpx.Response(
            200,
            json={
                "header": "SberBoom Home",
                "settings": [
                    {"id": "assistant_sounds_enabled", "type": "TOGGLE", "enabled": True},
                    {
                        "id": "led_brightness",
                        "type": "SLIDER",
                        "value": 50,
                        "min": 0,
                        "max": 100,
                        "unitSymbol": "%",
                    },
                ],
            },
        )

    api, _ = _build(handler)
    screen = await api.get_settings(PRODUCT, SERIAL)
    assert isinstance(screen, SettingScreenDto)
    assert screen.header == "SberBoom Home"
    toggle = screen.settings[0]
    assert toggle.type == "TOGGLE"
    assert toggle.current_value is True
    slider = screen.settings[1]
    assert slider.minimum == 0 and slider.maximum == 100
    assert slider.unit == "%"
    assert slider.current_value == 50


# ----- get_settings со screen: попадает в тело -----
@pytest.mark.asyncio
async def test_get_settings_with_screen_includes_it():
    def handler(req):
        assert _json(req).get("screen") == "child_section"
        return httpx.Response(200, json={"header": "child", "settings": []})

    api, _ = _build(handler)
    await api.get_settings(PRODUCT, SERIAL, screen="child_section")


# ----- get_settings_deep: раскрытие CARD-подэкранов -----
@pytest.mark.asyncio
async def test_get_settings_deep_expands_cards():
    def handler(req):
        screen = _json(req).get("screen")
        if screen is None:
            return httpx.Response(
                200,
                json={
                    "header": "root",
                    "settings": [
                        {"id": "child_section", "type": "CARD", "action": "openScreen"},
                    ],
                },
            )
        assert screen == "child_section"
        return httpx.Response(
            200,
            json={
                "header": "child",
                "settings": [
                    {"id": "age_mode", "type": "TOGGLE", "enabled": False},
                ],
            },
        )

    api, _ = _build(handler)
    screen = await api.get_settings_deep(PRODUCT, SERIAL)
    card = screen.settings[0]
    assert card.type == "CARD"
    # подэкран раскрыт в children
    ids = [c.id for c in card.children]
    assert "age_mode" in ids


# ----- рекурсия: защита от цикла (CARD на самого себя) -----
@pytest.mark.asyncio
async def test_get_settings_deep_cycle_guard():
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        # любой запрос возвращает тот же CARD, ссылающийся на себя
        return httpx.Response(
            200,
            json={
                "header": "loop",
                "settings": [{"id": "loop", "type": "CARD", "action": "openScreen"}],
            },
        )

    api, _ = _build(handler)
    await api.get_settings_deep(PRODUCT, SERIAL)  # не должно зациклиться
    # root + один раскрытый screen "loop" (второй раз seen блокирует)
    assert calls["n"] <= 3


# ----- set_setting: тело записи -----
@pytest.mark.asyncio
async def test_set_setting_body():
    def handler(req):
        assert req.url.path == "/v18/devices/settings/device"
        body = _json(req)
        assert body == {
            "product": PRODUCT,
            "serialNumber": SERIAL,
            "setting": [{"type": "TOGGLE", "id": "age_mode", "value": True}],
        }
        return httpx.Response(200, json={"state": {"status": 200}})

    api, _ = _build(handler)
    await api.set_setting(PRODUCT, SERIAL, "age_mode", "TOGGLE", True)


# ----- DTO serde: camelCase remap, radioButtons, current_value -----
def test_node_serde_radio_and_current_value():
    node = SettingNodeDto.from_dict(
        {
            "id": "age_mode",
            "type": "RADIO_BUTTONS",
            "checked": "adult",
            "radioButtons": [
                {"title": "Взрослый", "value": "adult"},
                {"title": "Детский", "value": "child"},
            ],
        }
    )
    assert node.current_value == "adult"
    assert [o.value for o in node.options] == ["adult", "child"]


def test_node_serde_ignores_unknown_and_survives():
    # неизвестные поля/типы не ломают парсинг
    node = SettingNodeDto.from_dict(
        {"id": "x", "type": "FUTURE_WIDGET", "totallyNew": {"a": 1}, "value": 7}
    )
    assert node.type == "FUTURE_WIDGET"
    assert node.current_value == 7
