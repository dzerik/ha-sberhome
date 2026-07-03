"""Tests for SberHome fan platform — sbermap-driven (PR #6 + bidirectional PR #9).

Проверяем:
- создание entities из coordinator.entities (Platform.FAN);
- маппинг state из reported_state (on_off/hvac_air_flow_power);
- preset modes из CategorySpec.options;
- командные методы → coordinator.async_send_device_state;
- edge cases: entity без options, пропавшая entity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.fan import FanEntityFeature
from homeassistant.const import STATE_OFF, Platform

from custom_components.sberhome.aiosber.dto import AttributeValueDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.fan import SberSbermapFan, async_setup_entry
from custom_components.sberhome.sbermap import HaEntityData

from .conftest import build_coordinator_caches

# Включённый вентилятор на средней скорости.
MOCK_FAN = {
    "id": "fan_1",
    "serial_number": "SN_FAN_001",
    "name": {"name": "Test Fan"},
    "image_set_type": "hvac_fan",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-FAN"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_air_flow_power", "enum_value": "medium"},
    ],
    "attributes": [],
}

# Выключенный вентилятор.
MOCK_FAN_OFF = {
    "id": "fan_off_1",
    "serial_number": "SN_FAN_002",
    "name": {"name": "Test Fan Off"},
    "image_set_type": "hvac_fan",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-FAN"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": False},
    ],
    "attributes": [],
}

# Не-fan устройство — не должно попасть в платформу.
MOCK_CURTAIN_DEVICE = {
    "id": "curtain_x_1",
    "serial_number": "SN_CURTAIN_X",
    "name": {"name": "Not A Fan"},
    "image_set_type": "curtain",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-CURTAIN"},
    "desired_state": [],
    "reported_state": [
        {"key": "open_state", "enum_value": "closed"},
    ],
    "attributes": [],
}


def _make_coordinator(raw_devices: dict) -> MagicMock:
    """Coordinator-mock: devices/entities кэши + StateCache + AsyncMock send."""
    coord = MagicMock()
    coord.data = raw_devices
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    cache = StateCache()
    cache.update_from_devices(coord.devices)
    coord.state_cache = cache
    coord.async_send_device_state = AsyncMock()
    return coord


def _fan_entity(coord: MagicMock, device_id: str) -> SberSbermapFan:
    """Построить SberSbermapFan из primary FAN entity устройства."""
    ent = next(e for e in coord.entities[device_id] if e.platform is Platform.FAN)
    return SberSbermapFan(coord, device_id, ent)


class TestAsyncSetupEntry:
    async def test_creates_entities_only_for_fan_platform(self):
        """Два вентилятора → 2 fan entities, curtain пропускается."""
        coord = _make_coordinator(
            {"fan_1": MOCK_FAN, "fan_off_1": MOCK_FAN_OFF, "curtain_x_1": MOCK_CURTAIN_DEVICE}
        )
        entry = MagicMock()
        entry.runtime_data = coord
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        assert len(captured) == 2
        assert all(isinstance(e, SberSbermapFan) for e in captured)
        assert {e._device_id for e in captured} == {"fan_1", "fan_off_1"}


class TestFanEntity:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"fan_1": MOCK_FAN})

    @pytest.fixture
    def entity(self, coord):
        return _fan_entity(coord, "fan_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "fan_1"

    def test_supported_features(self, entity):
        features = entity._attr_supported_features
        assert features & FanEntityFeature.TURN_ON
        assert features & FanEntityFeature.TURN_OFF
        assert features & FanEntityFeature.PRESET_MODE

    def test_preset_modes_from_category_spec(self, entity):
        """hvac_fan → options=("low", "medium", "high", "turbo") из CategorySpec."""
        assert entity._attr_preset_modes == ["low", "medium", "high", "turbo"]

    def test_is_on(self, entity):
        assert entity.is_on is True

    def test_preset_mode(self, entity):
        assert entity.preset_mode == "medium"


class TestFanOffEntity:
    def test_is_on_false(self):
        coord = _make_coordinator({"fan_off_1": MOCK_FAN_OFF})
        entity = _fan_entity(coord, "fan_off_1")
        assert entity.is_on is False


class TestFanWithoutPresets:
    def test_no_preset_mode_feature_when_no_options(self):
        """HaEntityData без options → PRESET_MODE feature не включается."""
        coord = _make_coordinator({"fan_1": MOCK_FAN})
        ha_entity = HaEntityData(
            platform=Platform.FAN,
            unique_id="fan_1",
            name="Simple Fan",
            state=STATE_OFF,
            sber_category="hvac_fan",
        )
        entity = SberSbermapFan(coord, "fan_1", ha_entity)
        assert not entity._attr_supported_features & FanEntityFeature.PRESET_MODE


class TestMissingEntity:
    """HaEntityData пропала из coordinator.entities — graceful None."""

    @pytest.fixture
    def entity(self):
        coord = _make_coordinator({"fan_1": MOCK_FAN})
        ent = _fan_entity(coord, "fan_1")
        coord.entities["fan_1"] = []
        return ent

    def test_is_on_is_none(self, entity):
        assert entity.is_on is None

    def test_preset_mode_is_none(self, entity):
        assert entity.preset_mode is None


class TestCommands:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"fan_1": MOCK_FAN})

    @pytest.fixture
    def entity(self, coord):
        return _fan_entity(coord, "fan_1")

    async def test_turn_on(self, coord, entity):
        await entity.async_turn_on()
        coord.async_send_device_state.assert_awaited_once_with(
            "fan_1", [AttributeValueDto.of_bool("on_off", True)]
        )

    async def test_turn_on_with_preset_mode(self, coord, entity):
        """turn_on с preset_mode шлёт on_off + hvac_air_flow_power одной командой."""
        await entity.async_turn_on(preset_mode="high")
        coord.async_send_device_state.assert_awaited_once_with(
            "fan_1",
            [
                AttributeValueDto.of_bool("on_off", True),
                AttributeValueDto.of_enum("hvac_air_flow_power", "high"),
            ],
        )

    async def test_turn_off(self, coord, entity):
        await entity.async_turn_off()
        coord.async_send_device_state.assert_awaited_once_with(
            "fan_1", [AttributeValueDto.of_bool("on_off", False)]
        )

    async def test_set_preset_mode(self, coord, entity):
        await entity.async_set_preset_mode("turbo")
        coord.async_send_device_state.assert_awaited_once_with(
            "fan_1", [AttributeValueDto.of_enum("hvac_air_flow_power", "turbo")]
        )
