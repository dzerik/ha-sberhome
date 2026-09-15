"""Настройки умных колонок в настоящем Home Assistant: сущности из канала /v18."""

from __future__ import annotations

import json

import httpx
from homeassistant.const import STATE_ON, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.sberhome.const import (
    CONF_ENABLED_DEVICE_UIDS,
    DOMAIN,
    SPEAKER_MERGE_DOMAIN,
)

from .fake_cloud import FakeSberCloud, device

SCREEN = {
    "header": "SberBoom",
    "settings": [
        {"id": "child", "type": "TOGGLE", "title": "Детский режим", "enabled": True},
        {
            "id": "hint_volume",
            "type": "SLIDER",
            "title": "Громкость подсказок",
            "min": 0,
            "max": 10,
        },
        {
            "id": "theme",
            "type": "RADIO_BUTTONS",
            "title": "Тема",
            "radioButtons": [
                {"title": "Тёмная", "value": "dark"},
                {"title": "Светлая", "value": "light"},
            ],
        },
    ],
}


def _settings(request: httpx.Request) -> httpx.Response:
    serial = json.loads(request.content)["serialNumber"]
    if serial == "SN-boom":
        return httpx.Response(200, json=SCREEN)
    # Экрана нет (у прошивки нет настроек) — сущностей у колонки не будет.
    return httpx.Response(200, json=None)


def _entity_state(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert entity_id is not None, (platform, unique_id)
    return hass.states.get(entity_id).state


async def test_speaker_settings_become_entities_on_the_speaker_device(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    fake_cloud.devices = [
        device(
            "boom",
            image_set_type="dt_boom",
            serial="SN-boom",
            reported=[{"key": "online", "type": "BOOL", "bool_value": True}],
        )
    ]
    fake_cloud.on(
        "POST",
        "/v18/devices",
        {
            "devices": [
                {"deviceId": "d1", "serialNumber": "SN-boom", "product": "sberboom"},
                {"deviceId": "d2", "serialNumber": "SN-mini", "product": "unknown_speaker"},
                {"deviceId": "d3", "product": "sberboom"},
            ]
        },
    )
    fake_cloud.on("POST", "/v18/devices/settings", _settings)

    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-boom"]})

    coordinator = entry.runtime_data
    assert set(coordinator.staros_settings_entities) == {"SN-boom"}
    assert _entity_state(hass, "switch", "staros_SN-boom_child") == STATE_ON
    # Значение не пришло — HA показывает «неизвестно», а не ноль или первый пункт.
    assert _entity_state(hass, "number", "staros_SN-boom_hint_volume") == STATE_UNKNOWN
    assert _entity_state(hass, "select", "staros_SN-boom_theme") == STATE_UNKNOWN

    # Колонка — одна карточка с sboom_ha: общий идентификатор по серийнику.
    speaker = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, "SN-boom")})
    assert speaker is not None
    assert (SPEAKER_MERGE_DOMAIN, "SN-boom") in speaker.identifiers
