"""Переклейка unique_id после смены облачного идентификатора устройства.

Без неё починка выбора делает хуже, чем было. Раньше устройство с новым
идентификатором просто удалялось из реестра целиком, и Home Assistant каскадом
уносил сущности — установка обнулялась, но оставалась связной. Теперь запись
устройства выживает, и старые сущности остались бы висеть навсегда
недоступными, а новые приехали бы с entity_id вида `..._2`, сломав все
автоматизации пользователя.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.unique_id_repair import async_repair_rotated_unique_ids

SERIAL = "37304b41500100001532623a"
OLD_ID = "cloud-old"
NEW_ID = "cloud-new"


def _dto(device_id: str) -> DeviceDto:
    return DeviceDto.from_dict(
        {"id": device_id, "serial_number": SERIAL, "name": {"name": "Лампа"}}
    )


def _coordinator(suffixes: list[str]) -> MagicMock:
    coord = MagicMock()
    dto = _dto(NEW_ID)
    coord.enabled_devices = {NEW_ID: dto}
    coord.devices = {NEW_ID: dto}
    coord.entities = {NEW_ID: [MagicMock(unique_id=f"{NEW_ID}_{suffix}") for suffix in suffixes]}
    return coord


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=DOMAIN, entry_id="e1")
    config_entry.add_to_hass(hass)
    return config_entry


@pytest.fixture
def device(hass: HomeAssistant, entry: MockConfigEntry) -> dr.DeviceEntry:
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, SERIAL)}
    )


async def test_rotated_prefix_is_renamed(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Ключ меняется, а entity_id и имя остаются — иначе ломаются автоматизации."""
    record = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{OLD_ID}_battery", config_entry=entry, device_id=device.id
    )
    entity_registry.async_update_entity(record.entity_id, name="Батарея лампы")
    entity_id = record.entity_id

    renamed = await async_repair_rotated_unique_ids(hass, entry, _coordinator(["battery"]))

    assert renamed == 1
    updated = entity_registry.async_get(entity_id)
    assert updated is not None
    assert updated.unique_id == f"{NEW_ID}_battery"
    assert updated.name == "Батарея лампы"


async def test_primary_entity_without_suffix_is_renamed(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """У основной сущности ключ равен самому идентификатору устройства."""
    record = entity_registry.async_get_or_create(
        "binary_sensor", DOMAIN, OLD_ID, config_entry=entry, device_id=device.id
    )

    await async_repair_rotated_unique_ids(hass, entry, _coordinator(["battery"]))

    assert entity_registry.async_get(record.entity_id).unique_id == NEW_ID


async def test_longest_suffix_wins(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """`_power_state` не должен схлопнуться в `_state` и забрать чужой ключ."""
    record = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{OLD_ID}_power_state", config_entry=entry, device_id=device.id
    )

    await async_repair_rotated_unique_ids(hass, entry, _coordinator(["state", "power_state"]))

    assert entity_registry.async_get(record.entity_id).unique_id == f"{NEW_ID}_power_state"


async def test_current_entities_are_left_alone(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Обычный случай — идентификатор не менялся, трогать нечего."""
    record = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{NEW_ID}_battery", config_entry=entry, device_id=device.id
    )

    renamed = await async_repair_rotated_unique_ids(hass, entry, _coordinator(["battery"]))

    assert renamed == 0
    assert entity_registry.async_get(record.entity_id).unique_id == f"{NEW_ID}_battery"


async def test_occupied_target_is_skipped(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """Занятый ключ не перезаписываем: дубль лучше, чем упавшая настройка."""
    stale = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{OLD_ID}_battery", config_entry=entry, device_id=device.id
    )
    entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{NEW_ID}_battery", config_entry=entry, device_id=device.id
    )

    renamed = await async_repair_rotated_unique_ids(hass, entry, _coordinator(["battery"]))

    assert renamed == 0
    assert entity_registry.async_get(stale.entity_id).unique_id == f"{OLD_ID}_battery"


async def test_other_config_entry_is_untouched(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    entry: MockConfigEntry,
    device: dr.DeviceEntry,
) -> None:
    """У пользователя может быть два аккаунта Сбера."""
    other = MockConfigEntry(domain=DOMAIN, entry_id="e2")
    other.add_to_hass(hass)
    foreign = entity_registry.async_get_or_create(
        "sensor", DOMAIN, f"{OLD_ID}_battery", config_entry=other, device_id=device.id
    )

    renamed = await async_repair_rotated_unique_ids(hass, entry, _coordinator(["battery"]))

    assert renamed == 0
    assert entity_registry.async_get(foreign.entity_id).unique_id == f"{OLD_ID}_battery"
