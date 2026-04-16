"""Tests for SberHome light entity — sbermap-driven (PR #4 рефакторинга)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode

from custom_components.sberhome.light import SberLightEntity


@pytest.fixture
def coordinator(mock_coordinator_with_entities):
    """Coordinator с предзаполненными devices/entities + замоканный send_state."""
    coord = mock_coordinator_with_entities
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=coord.data)
    # get_sber_client возвращает client с mocked devices.set_state.
    fake_client = AsyncMock()
    fake_client.devices = AsyncMock()
    coord.home_api.get_sber_client = AsyncMock(return_value=fake_client)
    coord._fake_client = fake_client
    coord.async_set_updated_data = MagicMock()
    coord._rebuild_dto_caches = MagicMock()
    return coord


@pytest.fixture
def light_entity(coordinator):
    return SberLightEntity(coordinator, "device_light_1")


@pytest.fixture
def ledstrip_entity(coordinator):
    return SberLightEntity(coordinator, "device_ledstrip_1")


class TestState:
    def test_unique_id(self, light_entity):
        assert light_entity._attr_unique_id == "device_light_1"

    def test_name_is_none_for_primary(self, light_entity):
        assert light_entity._attr_name is None

    def test_is_on_true(self, light_entity):
        assert light_entity.is_on is True

    def test_supported_color_modes(self, light_entity):
        modes = light_entity.supported_color_modes
        assert ColorMode.HS in modes
        assert ColorMode.COLOR_TEMP in modes
        assert ColorMode.BRIGHTNESS not in modes

    def test_color_mode_white(self, light_entity):
        assert light_entity.color_mode is ColorMode.COLOR_TEMP

    def test_color_mode_colour(self, ledstrip_entity):
        assert ledstrip_entity.color_mode is ColorMode.HS

    def test_brightness_in_range(self, light_entity):
        b = light_entity.brightness
        assert b is not None
        assert 0 < b <= 255

    def test_color_temp_kelvin_in_range(self, light_entity):
        k = light_entity.color_temp_kelvin
        assert k is not None
        assert 2700 <= k <= 6500

    def test_min_max_color_temp_bulb(self, light_entity):
        assert light_entity.min_color_temp_kelvin == 2700
        assert light_entity.max_color_temp_kelvin == 6500

    def test_min_max_color_temp_ledstrip(self, ledstrip_entity):
        assert ledstrip_entity.min_color_temp_kelvin == 2000
        assert ledstrip_entity.max_color_temp_kelvin == 6500

    def test_hs_color(self, ledstrip_entity):
        c = ledstrip_entity.hs_color
        assert c is not None
        h, s = c
        assert 0 <= h <= 360
        assert 0 <= s <= 100


class TestCommands:
    @pytest.mark.asyncio
    async def test_turn_on_sends_on_off_true(self, light_entity, coordinator):
        await light_entity.async_turn_on()
        coordinator._fake_client.devices.set_state.assert_called_once()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is True for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_off_sends_on_off_false(self, light_entity, coordinator):
        await light_entity.async_turn_off()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is False for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness(self, light_entity, coordinator):
        await light_entity.async_turn_on(brightness=128)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        keys = [a.key for a in attrs]
        # При brightness без явного цвета — используем mode из device.attributes.
        # bulb_sber поддерживает colour+white, fallback colour.
        assert "light_brightness" in keys
        assert "light_mode" in keys

    @pytest.mark.asyncio
    async def test_turn_on_with_hs_color(self, light_entity, coordinator):
        await light_entity.async_turn_on(hs_color=(180.0, 50.0))
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        # light_colour отправлено + light_mode=colour
        assert any(a.key == "light_colour" and a.color_value is not None for a in attrs)
        assert any(a.key == "light_mode" and a.enum_value == "colour" for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_on_with_color_temp(self, light_entity, coordinator):
        await light_entity.async_turn_on(color_temp_kelvin=4000)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "light_colour_temp" for a in attrs)
        assert any(a.key == "light_mode" and a.enum_value == "white" for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_on_with_white(self, light_entity, coordinator):
        await light_entity.async_turn_on(white=200)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "light_mode" and a.enum_value == "white" for a in attrs)
        assert any(a.key == "light_brightness" for a in attrs)
