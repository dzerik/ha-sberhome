"""Tests для discovery polling + SberHubSubdeviceCount sensor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.coordinator import (
    DISCOVER_POLL_INTERVAL_SEC,
    HUB_CATEGORIES,
)
from custom_components.sberhome.sensor import SberHubSubdeviceCount


# ---------------------------------------------------------------------------
# SberHubSubdeviceCount — извлечение counter'а из разных shapes
# ---------------------------------------------------------------------------


def _coord(discovery: dict | None = None) -> MagicMock:
    coord = MagicMock()
    dto = DeviceDto(id="hub-1")
    coord.devices = {"hub-1": dto}
    coord.state_cache.get_device = MagicMock(return_value=dto)
    coord.discovery_info = discovery or {}
    return coord


class TestSubdeviceCount:
    def test_devices_list_shape(self):
        coord = _coord({"hub-1": {"devices": [{"id": "x"}, {"id": "y"}, {"id": "z"}]}})
        sensor = SberHubSubdeviceCount(coord, "hub-1")
        assert sensor.native_value == 3

    def test_sub_devices_list_shape(self):
        coord = _coord({"hub-1": {"sub_devices": [{"a": 1}]}})
        sensor = SberHubSubdeviceCount(coord, "hub-1")
        assert sensor.native_value == 1

    def test_children_list_shape(self):
        coord = _coord({"hub-1": {"children": []}})
        sensor = SberHubSubdeviceCount(coord, "hub-1")
        assert sensor.native_value == 0

    def test_count_int_shape(self):
        coord = _coord({"hub-1": {"count": 7}})
        sensor = SberHubSubdeviceCount(coord, "hub-1")
        assert sensor.native_value == 7

    def test_no_discovery_yet(self):
        coord = _coord(None)
        sensor = SberHubSubdeviceCount(coord, "hub-1")
        assert sensor.native_value is None

    def test_garbled_payload_returns_none(self):
        coord = _coord({"hub-1": "broken"})
        sensor = SberHubSubdeviceCount(coord, "hub-1")
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# Coordinator hub detection + discovery polling
# ---------------------------------------------------------------------------


def test_hub_categories_contains_expected_set():
    assert "hub" in HUB_CATEGORIES
    assert "sber_speaker" in HUB_CATEGORIES
    assert "intercom" in HUB_CATEGORIES


@pytest.mark.asyncio
async def test_maybe_poll_discovery_throttled():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._discover_disabled = False
    coord._discover_last_poll_at = time.time() - 60
    api = MagicMock()
    api.discover = AsyncMock()
    coord._device_api = MagicMock(return_value=api)
    coord._hub_device_ids = MagicMock(return_value=["hub-1"])

    await SberHomeCoordinator._maybe_poll_discovery(coord)
    api.discover.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_discovery_runs_after_interval():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._discover_disabled = False
    coord._discover_last_poll_at = time.time() - DISCOVER_POLL_INTERVAL_SEC - 1
    api = MagicMock()
    api.discover = AsyncMock(return_value={"devices": [{"id": "sub-1"}]})
    coord._device_api = MagicMock(return_value=api)
    coord._hub_device_ids = MagicMock(return_value=["hub-1"])
    coord.discovery_info = {}

    await SberHomeCoordinator._maybe_poll_discovery(coord)
    api.discover.assert_awaited_once_with("hub-1")
    assert coord.discovery_info == {"hub-1": {"devices": [{"id": "sub-1"}]}}


@pytest.mark.asyncio
async def test_maybe_poll_discovery_skips_failing_devices():
    """Один хаб уронил discovery — другой подхватился, refresh не падает."""
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._discover_disabled = False
    coord._discover_last_poll_at = None
    api = MagicMock()
    api.discover = AsyncMock(
        side_effect=[
            RuntimeError("hub-1 down"),
            {"devices": [{"id": "good-1"}]},
        ]
    )
    coord._device_api = MagicMock(return_value=api)
    coord._hub_device_ids = MagicMock(return_value=["hub-1", "hub-2"])
    coord.discovery_info = {}

    await SberHomeCoordinator._maybe_poll_discovery(coord)
    # hub-1 пропущен, hub-2 в результате.
    assert coord.discovery_info == {"hub-2": {"devices": [{"id": "good-1"}]}}
    assert coord._discover_disabled is False
