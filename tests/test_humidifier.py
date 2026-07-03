"""Tests for SberHome humidifier platform — sbermap-driven (PR #6 + bidirectional PR #9).

Проверяем:
- создание entities из coordinator.entities (Platform.HUMIDIFIER);
- маппинг state из reported_state (on_off/hvac_humidity_set/hvac_air_flow_power);
- min/max humidity и available_modes из CategorySpec;
- командные методы → coordinator.async_send_device_state;
- edge cases: отсутствующий target, entity без options, пропавшая entity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.humidifier import HumidifierEntityFeature
from homeassistant.const import STATE_OFF, Platform

from custom_components.sberhome.aiosber.dto import AttributeValueDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.humidifier import SberSbermapHumidifier, async_setup_entry
from custom_components.sberhome.sbermap import HaEntityData

from .conftest import build_coordinator_caches

# Включённый увлажнитель: target 55%, текущая влажность 48.5%, режим auto.
MOCK_HUMIDIFIER = {
    "id": "hum_1",
    "serial_number": "SN_HUM_001",
    "name": {"name": "Test Humidifier"},
    "image_set_type": "hvac_humidifier",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-HUMID"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_humidity_set", "integer_value": 55},
        {"key": "humidity", "float_value": 48.5},
        {"key": "hvac_air_flow_power", "enum_value": "auto"},
    ],
    "attributes": [],
}

# Выключенный увлажнитель без target humidity в reported_state.
MOCK_HUMIDIFIER_OFF = {
    "id": "hum_off_1",
    "serial_number": "SN_HUM_002",
    "name": {"name": "Test Humidifier Off"},
    "image_set_type": "hvac_humidifier",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-HUMID"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": False},
    ],
    "attributes": [],
}

# Не-humidifier устройство — не должно попасть в платформу.
MOCK_FAN_DEVICE = {
    "id": "fan_x_1",
    "serial_number": "SN_FAN_X",
    "name": {"name": "Not A Humidifier"},
    "image_set_type": "hvac_fan",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-FAN"},
    "desired_state": [],
    "reported_state": [{"key": "on_off", "bool_value": True}],
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


def _humidifier_entity(coord: MagicMock, device_id: str) -> SberSbermapHumidifier:
    """Построить SberSbermapHumidifier из primary HUMIDIFIER entity устройства."""
    ent = next(e for e in coord.entities[device_id] if e.platform is Platform.HUMIDIFIER)
    return SberSbermapHumidifier(coord, device_id, ent)


class TestAsyncSetupEntry:
    async def test_creates_entities_only_for_humidifier_platform(self):
        """Два увлажнителя → 2 humidifier entities, hvac_fan пропускается."""
        coord = _make_coordinator(
            {
                "hum_1": MOCK_HUMIDIFIER,
                "hum_off_1": MOCK_HUMIDIFIER_OFF,
                "fan_x_1": MOCK_FAN_DEVICE,
            }
        )
        entry = MagicMock()
        entry.runtime_data = coord
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        assert len(captured) == 2
        assert all(isinstance(e, SberSbermapHumidifier) for e in captured)
        assert {e._device_id for e in captured} == {"hum_1", "hum_off_1"}


class TestHumidifierEntity:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"hum_1": MOCK_HUMIDIFIER})

    @pytest.fixture
    def entity(self, coord):
        return _humidifier_entity(coord, "hum_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "hum_1"

    def test_supported_features_modes(self, entity):
        assert entity._attr_supported_features & HumidifierEntityFeature.MODES

    def test_available_modes_from_category_spec(self, entity):
        """hvac_humidifier → options=("auto", "low", "medium", "high", "turbo")."""
        assert entity._attr_available_modes == ["auto", "low", "medium", "high", "turbo"]

    def test_humidity_range_from_category_spec(self, entity):
        """hvac_humidifier → min_value=30, max_value=80 из CategorySpec."""
        assert entity._attr_min_humidity == 30
        assert entity._attr_max_humidity == 80

    def test_is_on(self, entity):
        assert entity.is_on is True

    def test_target_humidity(self, entity):
        assert entity.target_humidity == 55

    def test_mode(self, entity):
        assert entity.mode == "auto"


class TestHumidifierOffEntity:
    @pytest.fixture
    def entity(self):
        coord = _make_coordinator({"hum_off_1": MOCK_HUMIDIFIER_OFF})
        return _humidifier_entity(coord, "hum_off_1")

    def test_is_on_false(self, entity):
        assert entity.is_on is False

    def test_target_humidity_none_without_reported_key(self, entity):
        """hvac_humidity_set отсутствует в reported_state → target None."""
        assert entity.target_humidity is None

    def test_mode_none_without_reported_key(self, entity):
        assert entity.mode is None


class TestHumidifierWithoutModes:
    def test_no_modes_feature_when_no_options(self):
        """HaEntityData без options → MODES feature не включается."""
        coord = _make_coordinator({"hum_1": MOCK_HUMIDIFIER})
        ha_entity = HaEntityData(
            platform=Platform.HUMIDIFIER,
            unique_id="hum_1",
            name="Simple Humidifier",
            state=STATE_OFF,
            sber_category="hvac_humidifier",
        )
        entity = SberSbermapHumidifier(coord, "hum_1", ha_entity)
        assert entity._attr_supported_features == HumidifierEntityFeature(0)


class TestMissingEntity:
    """HaEntityData пропала из coordinator.entities — graceful None."""

    @pytest.fixture
    def entity(self):
        coord = _make_coordinator({"hum_1": MOCK_HUMIDIFIER})
        ent = _humidifier_entity(coord, "hum_1")
        coord.entities["hum_1"] = []
        return ent

    def test_is_on_is_none(self, entity):
        assert entity.is_on is None

    def test_target_humidity_is_none(self, entity):
        assert entity.target_humidity is None

    def test_mode_is_none(self, entity):
        assert entity.mode is None


class TestCommands:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"hum_1": MOCK_HUMIDIFIER})

    @pytest.fixture
    def entity(self, coord):
        return _humidifier_entity(coord, "hum_1")

    async def test_set_humidity(self, coord, entity):
        await entity.async_set_humidity(60)
        coord.async_send_device_state.assert_awaited_once_with(
            "hum_1", [AttributeValueDto.of_int("hvac_humidity_set", 60)]
        )

    async def test_set_mode(self, coord, entity):
        await entity.async_set_mode("high")
        coord.async_send_device_state.assert_awaited_once_with(
            "hum_1", [AttributeValueDto.of_enum("hvac_air_flow_power", "high")]
        )

    async def test_turn_on(self, coord, entity):
        await entity.async_turn_on()
        coord.async_send_device_state.assert_awaited_once_with(
            "hum_1", [AttributeValueDto.of_bool("on_off", True)]
        )

    async def test_turn_off(self, coord, entity):
        await entity.async_turn_off()
        coord.async_send_device_state.assert_awaited_once_with(
            "hum_1", [AttributeValueDto.of_bool("on_off", False)]
        )
