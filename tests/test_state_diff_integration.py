"""End-to-end: a WS DEVICE_STATE push records a state diff on the coordinator.

Guards the single integration promise of this feature: every real
inbound change produces exactly one ``StateDiff`` entry the panel can
render.  A miss here means DevTools would silently lie about what
actually changed between two pushes.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber import SocketMessageDto
from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.dto.state import AttributeValueDto, StateDto
from custom_components.sberhome.aiosber.dto.values import AttributeValueType
from custom_components.sberhome.api import HomeAPI, SberAPI
from custom_components.sberhome.coordinator import SberHomeCoordinator


@pytest.fixture
def coordinator():
    hass = MagicMock()
    hass.data = {}
    hass.loop = AsyncMock()
    hass.async_create_task = MagicMock()

    entry = MagicMock()
    entry.options = {}

    sber_api = AsyncMock(spec=SberAPI)
    home_api = AsyncMock(spec=HomeAPI)
    home_api.get_cached_devices = MagicMock(return_value={})
    home_api.get_cached_tree = MagicMock(return_value=None)

    coord = SberHomeCoordinator(hass, entry, sber_api, home_api)
    coord.async_set_updated_data = MagicMock()
    return coord


def _dto_with_temp(value: int) -> DeviceDto:
    return DeviceDto(
        id="dev-1",
        image_set_type="cat_sensor_temp_humidity",
        reported_state=[
            AttributeValueDto(
                key="temperature",
                type=AttributeValueType.INTEGER,
                integer_value=value,
            ),
        ],
    )


def _msg_with_temp(value: int) -> SocketMessageDto:
    return SocketMessageDto(
        state=StateDto(
            device_id="dev-1",
            reported_state=[
                AttributeValueDto(
                    key="temperature",
                    type=AttributeValueType.INTEGER,
                    integer_value=value,
                ),
            ],
        ),
    )


class TestWsPushRecordsDiff:
    async def test_second_push_with_different_value_records_diff(self, coordinator) -> None:
        coordinator.state_cache._devices = {"dev-1": _dto_with_temp(200)}
        coordinator.entities = {}

        # First push — same value as the DTO baseline; collector sees its
        # first snapshot for the device, records the baseline silently.
        await coordinator._on_ws_device_state(_msg_with_temp(200))
        assert coordinator.diff_collector.snapshot() == []

        # Second push — real temperature change.  One delta must land.
        await coordinator._on_ws_device_state(_msg_with_temp(225))
        snap = coordinator.diff_collector.snapshot()
        assert len(snap) == 1
        d = snap[0]
        assert d["device_id"] == "dev-1"
        assert d["source"] == "ws_push"
        assert d["topic"] == "DEVICE_STATE"
        # Before/after must both be present — missing "before" turns the
        # UI into a guessing game.
        assert d["changed"]["temperature"]["before"]["integer_value"] == 200
        assert d["changed"]["temperature"]["after"]["integer_value"] == 225

    async def test_identical_pushes_produce_no_diffs(self, coordinator) -> None:
        coordinator.state_cache._devices = {"dev-1": _dto_with_temp(200)}
        coordinator.entities = {}
        await coordinator._on_ws_device_state(_msg_with_temp(200))
        await coordinator._on_ws_device_state(_msg_with_temp(200))
        await coordinator._on_ws_device_state(_msg_with_temp(200))
        # Repeated identical pushes are the common case while a sensor sits
        # idle.  The collector must ignore them, otherwise the log would
        # scroll with empty "nothing changed" rows.
        assert coordinator.diff_collector.snapshot() == []


class TestCollectorExposedOnCoordinator:
    def test_coordinator_exposes_diff_collector(self, coordinator) -> None:
        # WS handlers reach the collector through this one attribute.
        # Renaming would silently break the DevTools panel.
        assert coordinator.diff_collector is not None
        assert coordinator.diff_collector.snapshot() == []
