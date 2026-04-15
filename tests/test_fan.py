"""Tests for the SberHome fan platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.fan import FanEntityFeature

from custom_components.sberhome.fan import SberGenericFan, async_setup_entry
from custom_components.sberhome.registry import CATEGORY_FANS


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def fan_entity(coordinator):
    return SberGenericFan(coordinator, "device_hvac_fan_1", CATEGORY_FANS["hvac_fan"])


class TestSberFan:
    def test_unique_id(self, fan_entity):
        assert fan_entity._attr_unique_id == "device_hvac_fan_1"

    def test_name(self, fan_entity):
        assert fan_entity._attr_name is None

    def test_supported_features(self, fan_entity):
        sf = fan_entity._attr_supported_features
        assert sf & FanEntityFeature.TURN_ON
        assert sf & FanEntityFeature.TURN_OFF
        assert sf & FanEntityFeature.PRESET_MODE

    def test_preset_modes(self, fan_entity):
        assert fan_entity._attr_preset_modes == ["low", "medium", "high", "turbo"]

    def test_is_on_true(self, fan_entity):
        assert fan_entity.is_on is True

    def test_is_on_false(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_fan_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": False}]
        coordinator.data["device_hvac_fan_1"] = dev
        entity = SberGenericFan(coordinator, "device_hvac_fan_1", CATEGORY_FANS["hvac_fan"])
        assert entity.is_on is False

    def test_is_on_no_state(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_fan_1"])
        dev["desired_state"] = []
        coordinator.data["device_hvac_fan_1"] = dev
        entity = SberGenericFan(coordinator, "device_hvac_fan_1", CATEGORY_FANS["hvac_fan"])
        assert entity.is_on is False

    def test_preset_mode(self, fan_entity):
        assert fan_entity.preset_mode == "medium"

    def test_preset_mode_none(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_fan_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": True}]
        coordinator.data["device_hvac_fan_1"] = dev
        entity = SberGenericFan(coordinator, "device_hvac_fan_1", CATEGORY_FANS["hvac_fan"])
        assert entity.preset_mode is None

    @pytest.mark.asyncio
    async def test_turn_on(self, fan_entity, coordinator):
        await fan_entity.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_fan_1", [{"key": "on_off", "bool_value": True}]
        )

    @pytest.mark.asyncio
    async def test_turn_on_with_preset(self, fan_entity, coordinator):
        await fan_entity.async_turn_on(preset_mode="high")
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_fan_1",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "hvac_air_flow_power", "enum_value": "high"},
            ],
        )

    @pytest.mark.asyncio
    async def test_turn_off(self, fan_entity, coordinator):
        await fan_entity.async_turn_off()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_fan_1", [{"key": "on_off", "bool_value": False}]
        )

    @pytest.mark.asyncio
    async def test_set_preset_mode(self, fan_entity, coordinator):
        await fan_entity.async_set_preset_mode("turbo")
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_fan_1", [{"key": "hvac_air_flow_power", "enum_value": "turbo"}]
        )
        coordinator.async_set_updated_data.assert_called_once()


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_fan_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # hvac_fan + hvac_air_purifier (humidifier is separate platform)
        assert len(entities) == 2
        ids = {e._device_id for e in entities}
        assert ids == {"device_hvac_fan_1", "device_hvac_purifier_1"}
