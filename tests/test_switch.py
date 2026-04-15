"""Tests for SberHome switch entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.coordinator import SberHomeCoordinator
from custom_components.sberhome.switch import SberSwitchEntity


@pytest.fixture
def mock_coordinator(mock_devices):
    coordinator = MagicMock(spec=SberHomeCoordinator)
    coordinator.data = mock_devices
    coordinator.home_api = AsyncMock()
    coordinator.home_api.get_cached_devices = MagicMock(return_value=mock_devices)
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


@pytest.fixture
def switch_entity(mock_coordinator):
    return SberSwitchEntity(mock_coordinator, "device_switch_1")


class TestSberSwitchEntity:
    def test_unique_id(self, switch_entity):
        assert switch_entity.unique_id == "device_switch_1"

    def test_name(self, switch_entity):
        assert switch_entity.name is None  # primary entity inherits device name

    def test_is_on(self, switch_entity):
        assert switch_entity.is_on is True

    def test_device_info(self, switch_entity):
        info = switch_entity.device_info
        assert info is not None
        assert info["manufacturer"] == "Sber"
        assert info["model"] == "SBDV-00154"

    @pytest.mark.asyncio
    async def test_turn_on(self, switch_entity, mock_coordinator):
        await switch_entity.async_turn_on()
        mock_coordinator.home_api.set_device_state.assert_called_once_with(
            "device_switch_1", [{"key": "on_off", "bool_value": True}]
        )
        mock_coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, switch_entity, mock_coordinator):
        await switch_entity.async_turn_off()
        mock_coordinator.home_api.set_device_state.assert_called_once_with(
            "device_switch_1", [{"key": "on_off", "bool_value": False}]
        )
        mock_coordinator.async_set_updated_data.assert_called_once()
