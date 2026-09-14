"""Незавершённые команды закрываются по таймеру, а не только на тике опроса.

``CommandTracker.sweep()`` вызывался лишь из обновления координатора. Пока
WebSocket жив, опрос идёт раз в 600 секунд, и команда, на которую облако
промолчало, висела «pending» до десяти минут вместо заявленных десяти
секунд.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.sberhome.command_tracker import CommandTracker
from custom_components.sberhome.coordinator import COMMAND_SWEEP_INTERVAL, SberHomeCoordinator


def _make_coordinator(hass: HomeAssistant) -> SberHomeCoordinator:
    coord = SberHomeCoordinator.__new__(SberHomeCoordinator)
    coord.hass = hass
    coord.command_tracker = CommandTracker(maxlen=10, command_timeout=0)
    return coord


async def test_pending_command_closes_without_polling(hass: HomeAssistant) -> None:
    coord = _make_coordinator(hass)
    unsub = coord.async_start_command_sweep()
    record = coord.command_tracker.record_sent(
        "dev-1", [{"key": "on_off", "type": "BOOL", "bool_value": True}]
    )

    async_fire_time_changed(hass, dt_util.utcnow() + COMMAND_SWEEP_INTERVAL)
    await hass.async_block_till_done()

    assert coord.command_tracker.get(record.command_id)["status"] == "silent_rejection"
    unsub()


async def test_sweep_stops_after_unsubscribe(hass: HomeAssistant) -> None:
    coord = _make_coordinator(hass)
    coord.async_start_command_sweep()()
    record = coord.command_tracker.record_sent(
        "dev-1", [{"key": "on_off", "type": "BOOL", "bool_value": True}]
    )

    async_fire_time_changed(hass, dt_util.utcnow() + COMMAND_SWEEP_INTERVAL * 3)
    await hass.async_block_till_done()

    assert coord.command_tracker.get(record.command_id)["status"] == "pending"
