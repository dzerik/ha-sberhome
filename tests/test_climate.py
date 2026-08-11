"""Tests for SberHome climate platform — sbermap-driven (PR #5 + bidirectional PR #9).

Проверяем:
- создание entities из coordinator.devices через climate_config_for;
- маппинг state из DeviceDto (hvac_mode/target/current temperature/fan_mode);
- командные методы → coordinator.async_send_device_state с правильными
  AttributeValueDto;
- edge cases: выключенное устройство, устройство без state_cache.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import ClimateEntityFeature, HVACMode

from custom_components.sberhome.aiosber.dto import AttributeValueDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.climate import SberClimateEntity, async_setup_entry
from custom_components.sberhome.sbermap import climate_config_for

from .conftest import build_coordinator_caches

# Кондиционер: полный набор features (hvac_modes + fan_modes).
# climate_state_from_dto читает on_off/hvac_temp_set/hvac_work_mode/
# hvac_air_flow_power из desired_state, temperature — из reported_state.
MOCK_AC = {
    "id": "ac_1",
    "serial_number": "SN_AC_001",
    "name": {"name": "Test AC"},
    "image_set_type": "hvac_ac",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-AC"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_temp_set", "integer_value": 24},
        {"key": "hvac_work_mode", "enum_value": "cool"},
        {"key": "hvac_air_flow_power", "enum_value": "auto"},
    ],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "temperature", "float_value": 22.5},
    ],
    "attributes": [],
}

# Кондиционер выключен (on_off=False в desired_state).
MOCK_AC_OFF = {
    "id": "ac_off_1",
    "serial_number": "SN_AC_002",
    "name": {"name": "Test AC Off"},
    "image_set_type": "hvac_ac",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-AC"},
    "desired_state": [
        {"key": "on_off", "bool_value": False},
        {"key": "hvac_temp_set", "integer_value": 22},
        {"key": "hvac_work_mode", "enum_value": "heat"},
    ],
    "reported_state": [
        {"key": "temperature", "float_value": 20.0},
    ],
    "attributes": [],
}

# Радиатор: минимальная конфигурация — без fan и без hvac_modes.
MOCK_RADIATOR = {
    "id": "radiator_1",
    "serial_number": "SN_RAD_001",
    "name": {"name": "Test Radiator"},
    "image_set_type": "hvac_radiator",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-RAD"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_temp_set", "integer_value": 30},
    ],
    "reported_state": [
        {"key": "temperature", "float_value": 27.0},
    ],
    "attributes": [],
}

# Не-climate устройство — не должно создавать climate entity.
MOCK_FAN_DEVICE = {
    "id": "fan_x_1",
    "serial_number": "SN_FAN_X",
    "name": {"name": "Not A Climate"},
    "image_set_type": "hvac_fan",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-FAN"},
    "desired_state": [],
    "reported_state": [{"key": "on_off", "bool_value": True}],
    "attributes": [],
}

# Устройство с неизвестной категорией — resolve_device_category → None.
MOCK_UNKNOWN_DEVICE = {
    "id": "unknown_1",
    "serial_number": "SN_UNKNOWN",
    "name": {"name": "Unknown Device"},
    "image_set_type": "totally_unknown_xyz",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-X"},
    "desired_state": [],
    "reported_state": [],
    "attributes": [],
}


def _make_coordinator(raw_devices: dict) -> MagicMock:
    """Coordinator-mock: devices/entities кэши + StateCache + AsyncMock send."""
    coord = MagicMock()
    coord.data = raw_devices
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    # Платформы обязаны читать enabled_devices, а не devices (issue #45).
    # В моке выбор не настроен, поэтому он совпадает с полным кэшем.
    coord.enabled_devices = coord.devices
    cache = StateCache()
    cache.update_from_devices(coord.devices)
    coord.state_cache = cache
    coord.async_send_device_state = AsyncMock()
    return coord


def _climate_entity(coord: MagicMock, device_id: str) -> SberClimateEntity:
    """Построить SberClimateEntity для устройства с конфигом его категории."""
    from custom_components.sberhome.sbermap import resolve_device_category

    category = resolve_device_category(coord.devices[device_id])
    config = climate_config_for(category)
    assert config is not None
    return SberClimateEntity(coord, device_id, config)


class TestAsyncSetupEntry:
    async def test_creates_entities_only_for_climate_categories(self):
        """AC + радиатор → 2 climate entities, hvac_fan и unknown пропускаются."""
        coord = _make_coordinator(
            {
                "ac_1": MOCK_AC,
                "radiator_1": MOCK_RADIATOR,
                "fan_x_1": MOCK_FAN_DEVICE,
                "unknown_1": MOCK_UNKNOWN_DEVICE,
            }
        )
        entry = MagicMock()
        entry.runtime_data = coord
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        assert len(captured) == 2
        assert all(isinstance(e, SberClimateEntity) for e in captured)
        assert {e._device_id for e in captured} == {"ac_1", "radiator_1"}


class TestAcEntity:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"ac_1": MOCK_AC})

    @pytest.fixture
    def entity(self, coord):
        return _climate_entity(coord, "ac_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "ac_1"

    def test_supported_features(self, entity):
        features = entity._attr_supported_features
        assert features & ClimateEntityFeature.TARGET_TEMPERATURE
        assert features & ClimateEntityFeature.TURN_ON
        assert features & ClimateEntityFeature.TURN_OFF
        assert features & ClimateEntityFeature.FAN_MODE

    def test_hvac_modes(self, entity):
        assert entity._attr_hvac_modes == [
            HVACMode.OFF,
            HVACMode.AUTO,
            HVACMode.COOL,
            HVACMode.HEAT,
            HVACMode.DRY,
            HVACMode.FAN_ONLY,
        ]

    def test_fan_modes(self, entity):
        assert entity._attr_fan_modes == ["auto", "low", "medium", "high", "turbo"]

    def test_temperature_limits_from_config(self, entity):
        assert entity._attr_min_temp == 16
        assert entity._attr_max_temp == 30
        assert entity._attr_target_temperature_step == 1

    def test_hvac_mode_cool(self, entity):
        assert entity.hvac_mode is HVACMode.COOL

    def test_target_temperature(self, entity):
        assert entity.target_temperature == 24.0

    def test_current_temperature(self, entity):
        assert entity.current_temperature == 22.5

    def test_fan_mode(self, entity):
        assert entity.fan_mode == "auto"


class TestAcOffEntity:
    def test_hvac_mode_off_when_device_off(self):
        """on_off=False → HVACMode.OFF независимо от hvac_work_mode."""
        coord = _make_coordinator({"ac_off_1": MOCK_AC_OFF})
        entity = _climate_entity(coord, "ac_off_1")
        assert entity.hvac_mode is HVACMode.OFF


class TestRadiatorEntity:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"radiator_1": MOCK_RADIATOR})

    @pytest.fixture
    def entity(self, coord):
        return _climate_entity(coord, "radiator_1")

    def test_no_fan_mode_feature(self, entity):
        assert not entity._attr_supported_features & ClimateEntityFeature.FAN_MODE

    def test_hvac_modes_fallback_to_heat(self, entity):
        """Категория без hvac_modes получает [OFF, HEAT] как fallback."""
        assert entity._attr_hvac_modes == [HVACMode.OFF, HVACMode.HEAT]

    def test_temperature_limits(self, entity):
        assert entity._attr_min_temp == 25
        assert entity._attr_max_temp == 40
        assert entity._attr_target_temperature_step == 5


class TestMissingDevice:
    """Устройство пропало из state_cache — state graceful degradation."""

    @pytest.fixture
    def entity(self):
        coord = _make_coordinator({"ac_1": MOCK_AC})
        ent = _climate_entity(coord, "ac_1")
        coord.state_cache._devices.pop("ac_1")
        return ent

    def test_hvac_mode_defaults_to_off(self, entity):
        assert entity.hvac_mode is HVACMode.OFF

    def test_temperatures_are_none(self, entity):
        assert entity.target_temperature is None
        assert entity.current_temperature is None

    def test_fan_mode_is_none(self, entity):
        assert entity.fan_mode is None


class TestCommands:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"ac_1": MOCK_AC})

    @pytest.fixture
    def entity(self, coord):
        return _climate_entity(coord, "ac_1")

    async def test_set_temperature(self, coord, entity):
        await entity.async_set_temperature(temperature=25.0)
        coord.async_send_device_state.assert_awaited_once_with(
            "ac_1", [AttributeValueDto.of_int("hvac_temp_set", 25)]
        )

    async def test_set_temperature_without_value_is_noop(self, coord, entity):
        """kwargs без ATTR_TEMPERATURE → команда не отправляется."""
        await entity.async_set_temperature()
        coord.async_send_device_state.assert_not_awaited()

    async def test_set_hvac_mode_cool(self, coord, entity):
        await entity.async_set_hvac_mode(HVACMode.COOL)
        coord.async_send_device_state.assert_awaited_once_with(
            "ac_1",
            [
                AttributeValueDto.of_bool("on_off", True),
                AttributeValueDto.of_enum("hvac_work_mode", "cool"),
            ],
        )

    async def test_set_hvac_mode_off(self, coord, entity):
        await entity.async_set_hvac_mode(HVACMode.OFF)
        coord.async_send_device_state.assert_awaited_once_with(
            "ac_1", [AttributeValueDto.of_bool("on_off", False)]
        )

    async def test_set_fan_mode(self, coord, entity):
        await entity.async_set_fan_mode("high")
        coord.async_send_device_state.assert_awaited_once_with(
            "ac_1", [AttributeValueDto.of_enum("hvac_air_flow_power", "high")]
        )

    async def test_turn_on(self, coord, entity):
        await entity.async_turn_on()
        coord.async_send_device_state.assert_awaited_once_with(
            "ac_1", [AttributeValueDto.of_bool("on_off", True)]
        )

    async def test_turn_off(self, coord, entity):
        await entity.async_turn_off()
        coord.async_send_device_state.assert_awaited_once_with(
            "ac_1", [AttributeValueDto.of_bool("on_off", False)]
        )


class TestRadiatorCommands:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"radiator_1": MOCK_RADIATOR})

    @pytest.fixture
    def entity(self, coord):
        return _climate_entity(coord, "radiator_1")

    async def test_set_hvac_mode_heat_without_work_mode_enum(self, coord, entity):
        """Категория без has_hvac_modes шлёт только on_off, без hvac_work_mode."""
        await entity.async_set_hvac_mode(HVACMode.HEAT)
        coord.async_send_device_state.assert_awaited_once_with(
            "radiator_1", [AttributeValueDto.of_bool("on_off", True)]
        )

    async def test_set_fan_mode_ignored_without_fan(self, coord, entity):
        """Радиатор без fan — async_set_fan_mode является no-op."""
        await entity.async_set_fan_mode("high")
        coord.async_send_device_state.assert_not_awaited()
