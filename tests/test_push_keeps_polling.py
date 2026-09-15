"""WebSocket-push'и не откладывают плановый опрос.

Штатный ``DataUpdateCoordinator.async_set_updated_data`` переносит следующий
плановый опрос на полный интервал от момента вызова и отменяет ожидающий
``async_request_refresh``. При живом WebSocket интервал опроса — 10 минут,
поэтому дом, где хоть одно устройство присылает push чаще, никогда не доходил
до полного опроса: не обновлялись сценарии, «Дома», OTA, индикатор, настройки
колонок, не удалялись пропавшие устройства и не подтягивались переименования.
"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.sberhome.aiosber import SocketMessageDto
from custom_components.sberhome.aiosber.auth import AuthManager
from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.dto.state import AttributeValueDto, StateDto
from custom_components.sberhome.aiosber.dto.values import AttributeValueType
from custom_components.sberhome.aiosber.transport import HttpTransport
from custom_components.sberhome.api import SberAPI
from custom_components.sberhome.const import DOMAIN, WS_CONNECTED_SCAN_INTERVAL
from custom_components.sberhome.coordinator import SberHomeCoordinator

DEVICE_ID = "dev-1"
WS_INTERVAL = timedelta(seconds=WS_CONNECTED_SCAN_INTERVAL)


def _temperature(value: int) -> AttributeValueDto:
    return AttributeValueDto(
        key="temperature", type=AttributeValueType.INTEGER, integer_value=value
    )


def _push(value: int, device_id: str = DEVICE_ID) -> SocketMessageDto:
    return SocketMessageDto(
        state=StateDto(device_id=device_id, reported_state=[_temperature(value)])
    )


@pytest.fixture
def coordinator(hass: HomeAssistant) -> SberHomeCoordinator:
    """Настоящий координатор с одним устройством; полный опрос подменён счётчиком."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="push-entry", options={})
    entry.add_to_hass(hass)
    coord = SberHomeCoordinator(
        hass,
        entry,
        AsyncMock(spec=SberAPI),
        AsyncMock(spec=HttpTransport),
        AsyncMock(spec=AuthManager),
    )
    coord.state_cache.update_from_flat(
        homes=[],
        rooms=[],
        groups=[],
        devices=[
            DeviceDto(
                id=DEVICE_ID,
                image_set_type="cat_sensor_temp_humidity",
                reported_state=[_temperature(200)],
            )
        ],
    )
    coord.data = coord._derive_data()
    # Интервал как при живом WebSocket.
    coord.update_interval = WS_INTERVAL
    coord._async_update_data = AsyncMock(side_effect=coord._derive_data)
    return coord


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


def _reported_temperature(coord: SberHomeCoordinator) -> int:
    attrs = coord.data[DEVICE_ID]["reported_state"]
    return next(a["integer_value"] for a in attrs if a["key"] == "temperature")


async def test_frequent_pushes_do_not_postpone_polling(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, coordinator: SberHomeCoordinator
) -> None:
    """Push раз в минуту на протяжении трёх интервалов — опрос идёт по расписанию."""
    unsub = coordinator.async_add_listener(MagicMock())
    update = coordinator._async_update_data

    minutes = 3 * WS_CONNECTED_SCAN_INTERVAL // 60 + 1
    for minute in range(minutes):
        await coordinator._on_ws_device_state(_push(200 + minute))
        await _advance(hass, freezer, 60)

    assert update.await_count == 3
    unsub()


async def test_push_updates_listeners_immediately(
    hass: HomeAssistant, coordinator: SberHomeCoordinator
) -> None:
    """Push сразу доходит до подписчиков (сущностей), без полного опроса."""
    seen: list[int] = []
    unsub = coordinator.async_add_listener(lambda: seen.append(_reported_temperature(coordinator)))
    handle = coordinator._unsub_refresh
    coordinator.last_update_success = False

    await coordinator._on_ws_device_state(_push(225))

    assert seen == [225]
    assert coordinator.last_update_success is True
    coordinator._async_update_data.assert_not_awaited()
    # Таймер опроса тот же, что был до push'а.
    assert coordinator._unsub_refresh is handle
    unsub()


async def test_push_keeps_pending_requested_refresh(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, coordinator: SberHomeCoordinator
) -> None:
    """Push не отменяет уже запрошенный (отложенный дебаунсером) полный опрос.

    Push неизвестного устройства просит полный опрос; второй такой запрос в
    окне дебаунсера откладывается. Раньше push известного устройства в этом
    окне отменял отложенный опрос, и новое устройство не появлялось до
    планового опроса через 10 минут.
    """
    unsub = coordinator.async_add_listener(MagicMock())
    update = coordinator._async_update_data

    await coordinator._on_ws_device_state(_push(1, device_id="new-dev"))
    await hass.async_block_till_done()
    await coordinator._on_ws_device_state(_push(2, device_id="new-dev"))
    await hass.async_block_till_done()
    assert update.await_count == 1

    await coordinator._on_ws_device_state(_push(230))
    await _advance(hass, freezer, 11)

    assert update.await_count == 2
    unsub()


async def test_push_rearms_stopped_polling(
    hass: HomeAssistant, coordinator: SberHomeCoordinator
) -> None:
    """Если таймер не взведён (опрос остановлен после сбоя), push взводит его снова."""
    unsub = coordinator.async_add_listener(MagicMock())
    coordinator._async_unsub_refresh()

    await coordinator._on_ws_device_state(_push(240))

    assert coordinator._unsub_refresh is not None
    unsub()


async def test_push_after_shutdown_does_not_schedule(
    hass: HomeAssistant, coordinator: SberHomeCoordinator
) -> None:
    """После выгрузки записи push не возобновляет опрос."""
    unsub = coordinator.async_add_listener(MagicMock())
    await coordinator.async_shutdown()

    await coordinator._on_ws_device_state(_push(250))

    assert coordinator._unsub_refresh is None
    unsub()


async def test_ws_interval_switch_applies_despite_pushes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, coordinator: SberHomeCoordinator
) -> None:
    """Смена интервала при подключении WS вступает в силу с ближайшего опроса.

    Пользовательский интервал 30 с; после подключения WS опрос переключает
    интервал на 10 минут. Частые push'и не мешают ни опросу на 30-й секунде,
    ни следующему — через 10 минут.
    """
    coordinator.update_interval = timedelta(seconds=30)
    update = coordinator._async_update_data

    async def _poll_switches_interval() -> dict:
        coordinator.update_interval = WS_INTERVAL
        return coordinator._derive_data()

    update.side_effect = _poll_switches_interval
    unsub = coordinator.async_add_listener(MagicMock())

    for second in range(0, 40, 5):
        await coordinator._on_ws_device_state(_push(300 + second))
        await _advance(hass, freezer, 5)
    assert update.await_count == 1

    for minute in range(WS_CONNECTED_SCAN_INTERVAL // 60):
        await coordinator._on_ws_device_state(_push(400 + minute))
        await _advance(hass, freezer, 60)
    assert update.await_count == 2
    unsub()


async def test_optimistic_update_after_command_keeps_timer(
    hass: HomeAssistant, coordinator: SberHomeCoordinator
) -> None:
    """Optimistic-обновление после команды сущности тоже не переносит опрос."""
    listener = MagicMock()
    unsub = coordinator.async_add_listener(listener)
    handle = coordinator._unsub_refresh

    coordinator.rebuild_caches_and_notify()

    listener.assert_called_once()
    assert coordinator._unsub_refresh is handle
    unsub()
