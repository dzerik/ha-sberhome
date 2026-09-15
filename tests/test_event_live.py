"""Event-сущности в настоящем Home Assistant: нажатия кнопок и срабатывания сценариев."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.sberhome.const import CONF_ENABLED_DEVICE_UIDS, DOMAIN
from custom_components.sberhome.intent_dispatcher import EVENT_SBERHOME_INTENT

from .fake_cloud import FakeSberCloud, device


def _entity_id(hass: HomeAssistant, unique_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id("event", DOMAIN, unique_id)
    assert entity_id is not None, unique_id
    return entity_id


def _press(value: str, last_sync: str | None) -> dict[str, Any]:
    attr: dict[str, Any] = {"key": "button_1_event", "type": "ENUM", "enum_value": value}
    if last_sync is not None:
        attr["last_sync"] = last_sync
    return attr


async def test_press_already_reported_at_startup_is_not_replayed(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    """Последнее нажатие из облака при запуске — прошлое: опрос его не повторяет.

    Раньше первое же обновление координатора после запуска HA или перезагрузки
    записи стреляло событием этого нажатия и запускало автоматизации.
    """
    fake_cloud.devices = [
        device("btn", image_set_type="scenario_button", reported=[_press("click", "t0")])
    ]
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-btn"]})
    entity_id = _entity_id(hass, "btn_button_1_event")

    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == STATE_UNKNOWN


async def test_button_press_pushes_fire_event_once_per_press(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    fake_cloud.devices = [
        device("btn", image_set_type="scenario_button", reported=[_press("click", "t0")])
    ]
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-btn"]})
    coordinator = entry.runtime_data
    entity_id = _entity_id(hass, "btn_button_1_event")

    async def push(value: str, last_sync: str | None) -> None:
        payload = {"state": {"device_id": "btn", "reported_state": [_press(value, last_sync)]}}
        await coordinator.async_inject_ws_message(payload, mark_replay=False)
        await hass.async_block_till_done()

    await push("click", "t1")
    first = hass.states.get(entity_id)
    assert first.attributes["event_type"] == "click"

    # Тот же push (то же нажатие) повторно не стреляет.
    await push("click", "t1")
    assert hass.states.get(entity_id).state == first.state

    await push("double_click", None)
    second = hass.states.get(entity_id)
    assert second.state != first.state
    assert second.attributes["event_type"] == "double_click"

    # Значение не из списка типов событий не стреляет.
    await push("unknown_gesture", None)
    assert hass.states.get(entity_id).state == second.state


async def test_scenario_event_fires_only_for_its_own_scenario(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    fake_cloud.scenarios = [{"id": "sc-1", "name": "Утро"}, {"id": "sc-2", "name": "Вечер"}]
    await setup_sberhome(options={})
    entity_id = _entity_id(hass, "sberhome_scenario_event_sc-1")

    hass.bus.async_fire(EVENT_SBERHOME_INTENT, {"scenario_id": "sc-2", "slug": None})
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNKNOWN

    hass.bus.async_fire(
        EVENT_SBERHOME_INTENT,
        {"scenario_id": "sc-1", "slug": None, "name": "Утро", "event_time": "2026-09-15T08:00:00Z"},
    )
    await hass.async_block_till_done()
    state = hass.states.get(entity_id)
    assert state.attributes["event_type"] == "triggered"
    assert state.attributes["name"] == "Утро"
