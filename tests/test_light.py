"""Tests for SberHome light entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode

from custom_components.sberhome.light import SberLightEntity
from custom_components.sberhome.coordinator import SberHomeCoordinator


@pytest.fixture
def mock_coordinator(mock_devices):
    coordinator = MagicMock(spec=SberHomeCoordinator)
    coordinator.data = mock_devices
    coordinator.home_api = AsyncMock()
    coordinator.home_api.get_cached_devices = MagicMock(return_value=mock_devices)
    coordinator.async_set_updated_data = MagicMock()
    return coordinator


@pytest.fixture
def light_entity(mock_coordinator):
    return SberLightEntity(mock_coordinator, "device_light_1", "bulb")


@pytest.fixture
def ledstrip_entity(mock_coordinator):
    return SberLightEntity(mock_coordinator, "device_ledstrip_1", "ledstrip")


class TestSberLightEntity:
    def test_unique_id(self, light_entity):
        assert light_entity.unique_id == "device_light_1"

    def test_name(self, light_entity):
        # has_entity_name=True: primary entity inherits device name from device_info
        assert light_entity.name is None

    def test_is_on(self, light_entity):
        assert light_entity.is_on is True

    def test_is_off(self, mock_coordinator):
        mock_coordinator.data["device_ledstrip_1"]["desired_state"][0]["bool_value"] = False
        entity = SberLightEntity(mock_coordinator, "device_ledstrip_1", "ledstrip")
        assert entity.is_on is False

    def test_supported_color_modes(self, light_entity):
        modes = light_entity.supported_color_modes
        assert ColorMode.HS in modes
        assert ColorMode.COLOR_TEMP in modes
        # BRIGHTNESS should NOT be separate when COLOR_TEMP/HS present
        assert ColorMode.BRIGHTNESS not in modes
        assert ColorMode.WHITE not in modes

    def test_color_mode_white(self, light_entity):
        assert light_entity.color_mode == ColorMode.COLOR_TEMP

    def test_color_mode_colour(self, ledstrip_entity):
        assert ledstrip_entity.color_mode == ColorMode.HS

    def test_brightness(self, light_entity):
        brightness = light_entity.brightness
        assert brightness is not None
        assert 0 < brightness <= 255

    def test_color_temp_kelvin(self, light_entity):
        kelvin = light_entity.color_temp_kelvin
        assert kelvin is not None
        assert 2700 <= kelvin <= 6500

    def test_min_max_color_temp_kelvin_bulb(self, light_entity):
        assert light_entity.min_color_temp_kelvin == 2700
        assert light_entity.max_color_temp_kelvin == 6500

    def test_min_max_color_temp_kelvin_ledstrip(self, ledstrip_entity):
        assert ledstrip_entity.min_color_temp_kelvin == 2000
        assert ledstrip_entity.max_color_temp_kelvin == 6500

    def test_hs_color(self, ledstrip_entity):
        color = ledstrip_entity.hs_color
        assert color is not None
        h, s = color
        assert 0 <= h <= 360
        assert 0 <= s <= 100

    def test_device_info(self, light_entity):
        info = light_entity.device_info
        assert info is not None
        assert info["manufacturer"] == "Sber"

    @pytest.mark.asyncio
    async def test_turn_on(self, light_entity, mock_coordinator):
        await light_entity.async_turn_on()
        mock_coordinator.home_api.set_device_state.assert_called_once()
        args = mock_coordinator.home_api.set_device_state.call_args
        states = args[0][1]
        assert any(s["key"] == "on_off" and s["bool_value"] is True for s in states)

    @pytest.mark.asyncio
    async def test_turn_off(self, light_entity, mock_coordinator):
        await light_entity.async_turn_off()
        mock_coordinator.home_api.set_device_state.assert_called_once()
        args = mock_coordinator.home_api.set_device_state.call_args
        states = args[0][1]
        assert any(s["key"] == "on_off" and s["bool_value"] is False for s in states)

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness(self, light_entity, mock_coordinator):
        await light_entity.async_turn_on(brightness=128)
        args = mock_coordinator.home_api.set_device_state.call_args
        states = args[0][1]
        assert any(s["key"] == "light_brightness" for s in states)

    @pytest.mark.asyncio
    async def test_turn_on_with_hs_color(self, light_entity, mock_coordinator):
        await light_entity.async_turn_on(hs_color=(180.0, 50.0))
        args = mock_coordinator.home_api.set_device_state.call_args
        states = args[0][1]
        assert any(s["key"] == "light_colour" for s in states)
        assert any(s.get("enum_value") == "colour" for s in states)

    @pytest.mark.asyncio
    async def test_turn_on_with_color_temp(self, light_entity, mock_coordinator):
        await light_entity.async_turn_on(color_temp_kelvin=4000)
        args = mock_coordinator.home_api.set_device_state.call_args
        states = args[0][1]
        assert any(s["key"] == "light_colour_temp" for s in states)
        assert any(s.get("enum_value") == "white" for s in states)

    @pytest.mark.asyncio
    async def test_turn_on_with_white(self, light_entity, mock_coordinator):
        await light_entity.async_turn_on(white=200)
        args = mock_coordinator.home_api.set_device_state.call_args
        states = args[0][1]
        assert any(s.get("enum_value") == "white" for s in states)
        assert any(s["key"] == "light_brightness" for s in states)
