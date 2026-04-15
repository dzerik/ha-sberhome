"""Tests for the SberHome humidifier platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.humidifier import (
    SberGenericHumidifier,
    async_setup_entry,
)
from custom_components.sberhome.registry import CATEGORY_HUMIDIFIERS


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def humidifier_entity(coordinator):
    return SberGenericHumidifier(
        coordinator, "device_humidifier_1", CATEGORY_HUMIDIFIERS["hvac_humidifier"]
    )


class TestSberHumidifier:
    def test_unique_id(self, humidifier_entity):
        assert humidifier_entity._attr_unique_id == "device_humidifier_1"

    def test_name(self, humidifier_entity):
        assert humidifier_entity._attr_name is None

    def test_min_max_humidity(self, humidifier_entity):
        assert humidifier_entity._attr_min_humidity == 30
        assert humidifier_entity._attr_max_humidity == 80

    def test_is_on_true(self, humidifier_entity):
        assert humidifier_entity.is_on is True

    def test_is_on_false(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_humidifier_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": False}]
        coordinator.data["device_humidifier_1"] = dev
        entity = SberGenericHumidifier(
            coordinator, "device_humidifier_1", CATEGORY_HUMIDIFIERS["hvac_humidifier"]
        )
        assert entity.is_on is False

    def test_target_humidity(self, humidifier_entity):
        assert humidifier_entity.target_humidity == 55

    def test_target_humidity_missing(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_humidifier_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": True}]
        coordinator.data["device_humidifier_1"] = dev
        entity = SberGenericHumidifier(
            coordinator, "device_humidifier_1", CATEGORY_HUMIDIFIERS["hvac_humidifier"]
        )
        assert entity.target_humidity is None

    def test_mode_reads_fan_power(self, humidifier_entity):
        # spec has mode_key=hvac_air_flow_power, desired_state fixture sets "medium"
        assert humidifier_entity.mode == "medium"

    @pytest.mark.asyncio
    async def test_turn_on(self, humidifier_entity, coordinator):
        await humidifier_entity.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_humidifier_1", [{"key": "on_off", "bool_value": True}]
        )

    @pytest.mark.asyncio
    async def test_turn_off(self, humidifier_entity, coordinator):
        await humidifier_entity.async_turn_off()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_humidifier_1", [{"key": "on_off", "bool_value": False}]
        )

    @pytest.mark.asyncio
    async def test_set_humidity(self, humidifier_entity, coordinator):
        await humidifier_entity.async_set_humidity(65)
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_humidifier_1",
            [{"key": "hvac_humidity_set", "integer_value": 65}],
        )
        coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_mode_sends_fan_power(self, humidifier_entity, coordinator):
        # hvac_humidifier теперь имеет mode_key=hvac_air_flow_power
        await humidifier_entity.async_set_mode("auto")
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_humidifier_1",
            [{"key": "hvac_air_flow_power", "enum_value": "auto"}],
        )


class TestHumidifierModes:
    """Новые фичи: mode_key=hvac_air_flow_power с 5 скоростями."""

    def test_available_modes_all_five(self, humidifier_entity):
        assert humidifier_entity._attr_available_modes == [
            "auto",
            "low",
            "medium",
            "high",
            "turbo",
        ]

    def test_supported_features_includes_modes(self, humidifier_entity):
        from homeassistant.components.humidifier import HumidifierEntityFeature

        assert (
            humidifier_entity._attr_supported_features & HumidifierEntityFeature.MODES
        )

    def test_mode_from_desired_state(self, humidifier_entity):
        """Fixture desired_state имеет hvac_air_flow_power=medium."""
        assert humidifier_entity.mode == "medium"

    def test_mode_missing_returns_none(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_humidifier_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": True}]
        coordinator.data["device_humidifier_1"] = dev
        entity = SberGenericHumidifier(
            coordinator, "device_humidifier_1", CATEGORY_HUMIDIFIERS["hvac_humidifier"]
        )
        assert entity.mode is None

    @pytest.mark.parametrize("mode", ["auto", "low", "medium", "high", "turbo"])
    @pytest.mark.asyncio
    async def test_set_mode_all_values(self, humidifier_entity, coordinator, mode):
        await humidifier_entity.async_set_mode(mode)
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_humidifier_1",
            [{"key": "hvac_air_flow_power", "enum_value": mode}],
        )


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_humidifier_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        assert len(entities) == 1
        assert entities[0]._device_id == "device_humidifier_1"
