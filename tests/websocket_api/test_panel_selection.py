"""Выбор устройств в панели: сохраняется ключами, переживает офлайн и импорт.

Команды идут через настоящий WebSocket и настоящую запись: сохранение выбора
перезагружает запись, поднимает или снимает сущности и чистит реестр.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import device_registry as dr

from custom_components.sberhome.const import (
    CONF_ENABLED_DEVICE_IDS,
    CONF_ENABLED_DEVICE_UIDS,
    DOMAIN,
)

from ..fake_cloud import FakeSberCloud, device
from .conftest import Panel


def _cloud_with_two_lamps(fake_cloud: FakeSberCloud) -> None:
    fake_cloud.devices = [
        device("lamp-1", reported=[{"key": "on_off", "type": "BOOL", "bool_value": True}]),
        device("lamp-2"),
        device("mystery", image_set_type="totally_unknown_thing"),
    ]


def _ha_device(hass: HomeAssistant, serial: str) -> dr.DeviceEntry | None:
    return dr.async_get(hass).async_get_device(identifiers={(DOMAIN, serial)})


async def test_toggle_on_and_off_persists_keys_and_manages_entities(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    _cloud_with_two_lamps(fake_cloud)
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: []})
    assert hass.states.get("light.lamp_1") is None

    response = await panel("toggle_device", device_id="lamp-1", enabled=True)

    assert response["result"] == {"success": True, "enabled": True, "total_enabled": 1}
    assert entry.state is ConfigEntryState.LOADED
    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == ["SN-lamp-1"]
    # Зеркало для старых версий — облачные id.
    assert entry.options[CONF_ENABLED_DEVICE_IDS] == ["lamp-1"]
    assert hass.states.get("light.lamp_1") is not None
    assert _ha_device(hass, "SN-lamp-1") is not None

    response = await panel("toggle_device", device_id="lamp-1", enabled=False)

    assert response["result"] == {"success": True, "enabled": False, "total_enabled": 0}
    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == []
    # Снятое устройство убрано из реестра сразу, вместе с сущностями.
    assert _ha_device(hass, "SN-lamp-1") is None
    assert hass.states.get("light.lamp_1") is None


async def test_toggle_keeps_selection_of_devices_missing_from_cloud(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    """Офлайн-устройство в сохранённом выборе не вычёркивается кликом по соседнему."""
    _cloud_with_two_lamps(fake_cloud)
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-offline", "SN-lamp-1"]})

    await panel("toggle_device", device_id="lamp-2", enabled=True)

    assert sorted(entry.options[CONF_ENABLED_DEVICE_UIDS]) == [
        "SN-lamp-1",
        "SN-lamp-2",
        "SN-offline",
    ]


async def test_toggle_on_legacy_entry_starts_from_all_devices(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    """Запись без сохранённого выбора показывала всё — снятие одного оставляет остальные."""
    _cloud_with_two_lamps(fake_cloud)
    entry = await setup_sberhome(options={})

    response = await panel("toggle_device", device_id="lamp-2", enabled=False)

    assert response["success"]
    assert sorted(entry.options[CONF_ENABLED_DEVICE_UIDS]) == ["SN-lamp-1", "SN-mystery"]


async def test_toggle_on_legacy_entry_enable_keeps_everything(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    _cloud_with_two_lamps(fake_cloud)
    entry = await setup_sberhome(options={})

    await panel("toggle_device", device_id="lamp-2", enabled=True)

    assert sorted(entry.options[CONF_ENABLED_DEVICE_UIDS]) == [
        "SN-lamp-1",
        "SN-lamp-2",
        "SN-mystery",
    ]


async def test_enabling_device_without_category_is_refused(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    _cloud_with_two_lamps(fake_cloud)
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: []})

    toggle = await panel("toggle_device", device_id="mystery", enabled=True)
    bulk = await panel("set_enabled", device_ids=["lamp-1", "mystery", "not-in-cloud"])

    assert toggle["error"]["code"] == "unsupported_category"
    assert bulk["error"]["code"] == "unsupported_category"
    assert "mystery" in bulk["error"]["message"]
    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == []


async def test_set_enabled_replaces_visible_selection_and_keeps_offline_keys(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    _cloud_with_two_lamps(fake_cloud)
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-offline", "SN-lamp-1"]})
    assert _ha_device(hass, "SN-lamp-1") is not None

    response = await panel("set_enabled", device_ids=["lamp-2"])

    assert response["result"] == {"success": True, "enabled_count": 1}
    assert sorted(entry.options[CONF_ENABLED_DEVICE_UIDS]) == ["SN-lamp-2", "SN-offline"]
    assert _ha_device(hass, "SN-lamp-1") is None
    assert hass.states.get("light.lamp_2") is not None


async def test_import_config_applies_settings_and_selection(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    _cloud_with_two_lamps(fake_cloud)
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp-1"]})
    exported = (await panel("export_config"))["result"]
    exported["enabled_device_uids"] = ["SN-lamp-2"]
    exported["settings"]["scan_interval"] = 120

    response = await panel("import_config", config=exported)

    assert response["result"] == {"success": True, "devices": 1}
    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == ["SN-lamp-2"]
    assert entry.options["scan_interval"] == 120
    assert _ha_device(hass, "SN-lamp-1") is None


async def test_set_device_area_moves_and_clears_area(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    _cloud_with_two_lamps(fake_cloud)
    await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp-1"]})
    area = ar.async_get(hass).async_create("Спальня")
    ha_device = _ha_device(hass, "SN-lamp-1")
    assert ha_device is not None

    moved = await panel("set_device_area", device_id="lamp-1", area_id=area.id)
    assert moved["result"] == {"success": True, "ha_device_id": ha_device.id, "area_id": area.id}
    assert dr.async_get(hass).async_get(ha_device.id).area_id == area.id

    cleared = await panel("set_device_area", device_id="lamp-1", area_id=None)
    assert cleared["success"]
    assert dr.async_get(hass).async_get(ha_device.id).area_id is None


async def test_set_device_area_for_device_not_in_home_assistant(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    _cloud_with_two_lamps(fake_cloud)
    await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp-1"]})

    response = await panel("set_device_area", device_id="lamp-2", area_id=None)

    assert response["error"]["code"] == "device_not_in_ha"
