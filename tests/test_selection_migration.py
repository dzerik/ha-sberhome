"""Перевод выбора устройств на стабильный ключ.

Цена ошибки здесь несимметрична. Не мигрировать вовремя — неприятно, но
безобидно: повторим на следующем опросе. Мигрировать по неполной выдаче — значит
молча выкинуть из выбора устройства, которых в ней не оказалось, и оставить
пользователя без сущностей. Поэтому тесты в основном про отказ от записи.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.const import (
    CONF_ENABLED_DEVICE_IDS,
    CONF_ENABLED_DEVICE_UIDS,
    CONF_SELECTION_MIRROR,
    DOMAIN,
)
from custom_components.sberhome.selection_migration import async_migrate_selection


def _dto(device_id: str, serial: str) -> DeviceDto:
    return DeviceDto.from_dict(
        {"id": device_id, "serial_number": serial, "name": {"name": device_id}}
    )


def _coordinator(devices: dict[str, DeviceDto], *, degraded: bool = False) -> MagicMock:
    coord = MagicMock()
    coord.devices = devices
    coord.state_cache.get_all_devices.return_value = devices
    coord.client.device_service.last_refresh_degraded = degraded
    return coord


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=DOMAIN, entry_id="e1", options={})
    config_entry.add_to_hass(hass)
    return config_entry


async def test_no_selection_keys_stays_passthrough(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Установка без выбора живёт в режиме «показывать всё».

    Любая запись превратила бы это в конкретный список и мгновенно скрыла у
    такого пользователя все устройства — самая дорогая регрессия из возможных.
    """
    coord = _coordinator({"A": _dto("A", "S")})

    assert await async_migrate_selection(hass, entry, coord) is True
    assert entry.options == {}


async def test_legacy_ids_become_serials(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(entry, options={CONF_ENABLED_DEVICE_IDS: ["A"]})
    coord = _coordinator({"A": _dto("A", "S")})

    assert await async_migrate_selection(hass, entry, coord) is True

    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == ["S"]
    # Зеркало из текущих облачных id — чтобы откат на предыдущую версию
    # интеграции прочитал привычный ей ключ и продолжил работать.
    assert entry.options[CONF_ENABLED_DEVICE_IDS] == ["A"]
    assert entry.options[CONF_SELECTION_MIRROR] == ["A"]


async def test_skipped_on_empty_cache(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(entry, options={CONF_ENABLED_DEVICE_IDS: ["A"]})
    coord = _coordinator({})

    assert await async_migrate_selection(hass, entry, coord) is False
    assert entry.options == {CONF_ENABLED_DEVICE_IDS: ["A"]}


async def test_skipped_on_degraded_refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Неполная выдача не повод переписывать выбор.

    Запасной путь опроса возвращает только дом по умолчанию: устройства прочих
    домов в выдаче отсутствуют, хотя в аккаунте они есть.
    """
    hass.config_entries.async_update_entry(entry, options={CONF_ENABLED_DEVICE_IDS: ["A", "Z"]})
    coord = _coordinator({"A": _dto("A", "S")}, degraded=True)

    assert await async_migrate_selection(hass, entry, coord) is False
    assert entry.options == {CONF_ENABLED_DEVICE_IDS: ["A", "Z"]}


async def test_unresolved_ids_are_carried_over(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Устройство может быть офлайн — его выбор нельзя терять."""
    hass.config_entries.async_update_entry(
        entry, options={CONF_ENABLED_DEVICE_IDS: ["A", "offline"]}
    )
    coord = _coordinator({"A": _dto("A", "S")})

    assert await async_migrate_selection(hass, entry, coord) is True
    assert set(entry.options[CONF_ENABLED_DEVICE_UIDS]) == {"S", "offline"}


async def test_empty_selection_is_preserved(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """«Выбрано ничего» — это выбор, а не отсутствие выбора."""
    hass.config_entries.async_update_entry(entry, options={CONF_ENABLED_DEVICE_IDS: []})
    coord = _coordinator({"A": _dto("A", "S")})

    assert await async_migrate_selection(hass, entry, coord) is True
    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == []


async def test_migration_is_idempotent(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(entry, options={CONF_ENABLED_DEVICE_IDS: ["A"]})
    coord = _coordinator({"A": _dto("A", "S")})

    await async_migrate_selection(hass, entry, coord)
    first = dict(entry.options)
    await async_migrate_selection(hass, entry, coord)

    assert dict(entry.options) == first


async def test_downgrade_write_is_respected(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    """Выбор, сделанный на откатившейся версии, авторитетен целиком.

    Та версия знает только старый ключ. Расхождение с копией зеркала значит,
    писали не мы, значит принимаем её выбор как есть — включая снятые галочки,
    иначе воскресили бы отключённое пользователем устройство.
    """
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_ENABLED_DEVICE_UIDS: ["S1", "S2"],
            CONF_ENABLED_DEVICE_IDS: ["A"],
            CONF_SELECTION_MIRROR: ["A", "B"],
        },
    )
    coord = _coordinator({"A": _dto("A", "S1"), "B": _dto("B", "S2")})

    assert await async_migrate_selection(hass, entry, coord) is True
    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == ["S1"]


async def test_own_write_is_left_alone(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    hass.config_entries.async_update_entry(
        entry,
        options={
            CONF_ENABLED_DEVICE_UIDS: ["S1"],
            CONF_ENABLED_DEVICE_IDS: ["A"],
            CONF_SELECTION_MIRROR: ["A"],
        },
    )
    coord = _coordinator({"A": _dto("A", "S1")})

    assert await async_migrate_selection(hass, entry, coord) is True
    assert entry.options[CONF_ENABLED_DEVICE_UIDS] == ["S1"]
