"""Tests for SberHome light entity — sbermap-driven (PR #4).

Базовые сценарии: создание, is_on, brightness, color state, turn_on/turn_off
команды и непустой supported_color_modes (HA 2025.3+ валидирует жёстко).

Эффекты покрыты в test_light_effects.py, параметризация supported_color_modes
от LightConfig — в test_light_color_modes.py. Здесь — реальные mock-девайсы
из conftest.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.light import ColorMode

from custom_components.sberhome.aiosber.dto import AttributeValueType
from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.light import (
    SberIndicatorLight,
    SberLightEntity,
    async_setup_entry,
)

from .conftest import MOCK_DEVICE_LEDSTRIP, MOCK_DEVICE_LIGHT


def _coord_with_raw(raw_devices: dict[str, dict]) -> MagicMock:
    """Coordinator-mock с реальными DeviceDto + StateCache из raw-словарей."""
    devices = {did: DeviceDto.from_dict(raw) for did, raw in raw_devices.items()}
    cache = StateCache()
    cache.update_from_devices(devices)
    coord = MagicMock()
    coord.devices = devices
    # Платформы обязаны читать enabled_devices, а не devices (issue #45).
    # В моке выбор не настроен, поэтому он совпадает с полным кэшем.
    coord.enabled_devices = devices
    coord.state_cache = cache
    coord.async_send_device_state = AsyncMock()
    return coord


@pytest.fixture
def light_coord() -> MagicMock:
    return _coord_with_raw(
        {
            "device_light_1": MOCK_DEVICE_LIGHT,
            "device_ledstrip_1": MOCK_DEVICE_LEDSTRIP,
        }
    )


@pytest.fixture
def bulb(light_coord) -> SberLightEntity:
    return SberLightEntity(light_coord, "device_light_1")


@pytest.fixture
def ledstrip(light_coord) -> SberLightEntity:
    return SberLightEntity(light_coord, "device_ledstrip_1")


class TestLightState:
    def test_unique_id(self, bulb):
        """unique_id лампы без суффикса — это id устройства."""
        assert bulb.unique_id == "device_light_1"

    def test_is_on_true(self, bulb):
        """on_off=true в состоянии → is_on True."""
        assert bulb.is_on is True

    def test_is_on_false(self, ledstrip):
        """on_off=false у ленты → is_on False."""
        assert ledstrip.is_on is False

    def test_brightness_white_mode(self, bulb):
        """White-mode: light_brightness 500 из диапазона 1..900 → ~142 в HA 0..255."""
        assert bulb.brightness == 142

    def test_hs_color_in_colour_mode(self, ledstrip):
        """Colour-mode лента: hs_color из light_colour (h=200, s=80)."""
        assert ledstrip.color_mode is ColorMode.HS
        assert ledstrip.hs_color == (200, 80)

    def test_color_temp_kelvin_in_white_mode(self, bulb):
        """White-mode: color_temp_kelvin в границах min/max Kelvin."""
        assert bulb.color_mode is ColorMode.COLOR_TEMP
        assert bulb.min_color_temp_kelvin <= bulb.color_temp_kelvin <= bulb.max_color_temp_kelvin


class TestSupportedColorModes:
    def test_not_empty(self, bulb, ledstrip):
        """Критично для HA 2025.3+: set никогда не пустой."""
        assert bulb.supported_color_modes
        assert ledstrip.supported_color_modes

    def test_hs_and_color_temp_for_full_bulb(self, bulb):
        """Лампа с colour+white и colour_temp → {HS, COLOR_TEMP}."""
        assert bulb.supported_color_modes == {ColorMode.HS, ColorMode.COLOR_TEMP}

    def test_color_mode_always_in_supported(self, bulb, ledstrip):
        """color_mode обязан входить в supported_color_modes — HA валидирует."""
        assert bulb.color_mode in bulb.supported_color_modes
        assert ledstrip.color_mode in ledstrip.supported_color_modes


class TestLightCommands:
    @pytest.mark.asyncio
    async def test_turn_on_sends_on_off_true(self, light_coord, bulb):
        """Plain turn_on → одиночный on_off=true (BOOL)."""
        await bulb.async_turn_on()
        light_coord.async_send_device_state.assert_awaited_once()
        device_id, attrs = light_coord.async_send_device_state.await_args.args
        assert device_id == "device_light_1"
        sent = {a.key: a for a in attrs}
        assert sent["on_off"].bool_value is True
        assert sent["on_off"].type is AttributeValueType.BOOL

    @pytest.mark.asyncio
    async def test_turn_on_with_brightness_scales_to_sber_range(self, light_coord, bulb):
        """brightness=255 (HA max) → light_brightness=900 (Sber max)."""
        await bulb.async_turn_on(brightness=255)
        _, attrs = light_coord.async_send_device_state.await_args.args
        sent = {a.key: a for a in attrs}
        assert sent["on_off"].bool_value is True
        assert sent["light_brightness"].integer_value == 900

    @pytest.mark.asyncio
    async def test_turn_on_with_color_temp_switches_to_white(self, light_coord, bulb):
        """color_temp_kelvin → light_mode=white + light_colour_temp."""
        await bulb.async_turn_on(color_temp_kelvin=4000)
        _, attrs = light_coord.async_send_device_state.await_args.args
        sent = {a.key: a for a in attrs}
        assert sent["light_mode"].enum_value == "white"
        assert sent["light_colour_temp"].integer_value is not None

    @pytest.mark.asyncio
    async def test_turn_off_sends_on_off_false(self, light_coord, bulb):
        """turn_off → одиночный on_off=false."""
        await bulb.async_turn_off()
        device_id, attrs = light_coord.async_send_device_state.await_args.args
        assert device_id == "device_light_1"
        assert len(attrs) == 1
        assert attrs[0].key == "on_off"
        assert attrs[0].bool_value is False


class TestAvailability:
    def test_unavailable_when_reported_offline(self):
        """online=false в reported_state → available False."""
        raw = copy.deepcopy(MOCK_DEVICE_LIGHT)
        raw["reported_state"].append({"key": "online", "bool_value": False})
        coord = _coord_with_raw({"device_light_1": raw})
        light = SberLightEntity(coord, "device_light_1")
        assert light.available is False

    def test_unavailable_when_device_missing_from_cache(self, light_coord, bulb):
        """Устройство пропало из StateCache → available False."""
        light_coord.state_cache = StateCache()  # пустой кеш
        assert bulb.available is False


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_lights_and_indicator(self, light_coord):
        """Setup: по SberLightEntity на лампу/ленту + один SberIndicatorLight."""
        entry = MagicMock()
        entry.runtime_data = light_coord
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        lights = [e for e in captured if isinstance(e, SberLightEntity)]
        indicators = [e for e in captured if isinstance(e, SberIndicatorLight)]
        assert {light._device_id for light in lights} == {
            "device_light_1",
            "device_ledstrip_1",
        }
        assert len(indicators) == 1
