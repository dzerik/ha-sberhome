"""Tests for SberHome HVAC sensors (temperature/humidity/water_level from reported_state)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.sberhome.registry import CATEGORY_SENSORS, SensorSpec
from custom_components.sberhome.sensor import (
    SberGenericSensor,
    async_setup_entry,
)


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


def _spec(category: str, key: str) -> SensorSpec:
    for s in CATEGORY_SENSORS[category]:
        if s.key == key:
            return s
    raise KeyError(f"{category}/{key}")


class TestHvacACCurrentSensors:
    """hvac_ac → temperature + humidity (current from reported_state)."""

    def test_temperature_sensor(self, coordinator):
        entity = SberGenericSensor(
            coordinator, "device_hvac_ac_1", _spec("hvac_ac", "temperature")
        )
        assert entity.device_class == SensorDeviceClass.TEMPERATURE
        assert entity.native_value == 22.5

    def test_humidity_sensor(self, coordinator):
        entity = SberGenericSensor(
            coordinator, "device_hvac_ac_1", _spec("hvac_ac", "humidity")
        )
        assert entity.device_class == SensorDeviceClass.HUMIDITY
        assert entity.native_value == 45.0


class TestHvacHeaterRadiatorBoilerUnderfloor:
    """Теплогенераторы: temperature sensor из reported_state."""

    @pytest.mark.parametrize(
        "device_id,category,expected",
        [
            ("device_hvac_heater_1", "hvac_heater", 21.0),
            ("device_hvac_radiator_1", "hvac_radiator", 27.0),
            ("device_hvac_boiler_1", "hvac_boiler", 55.0),
            ("device_hvac_underfloor_1", "hvac_underfloor_heating", 30.0),
        ],
    )
    def test_temperature(self, coordinator, device_id, category, expected):
        entity = SberGenericSensor(
            coordinator, device_id, _spec(category, "temperature")
        )
        assert entity.device_class == SensorDeviceClass.TEMPERATURE
        assert entity.native_value == expected
        assert entity._attr_unique_id == f"{device_id}_temperature"


class TestHumidifierSensors:
    """hvac_humidifier → humidity, water_level, water_percentage."""

    def test_humidity(self, coordinator):
        entity = SberGenericSensor(
            coordinator, "device_humidifier_1", _spec("hvac_humidifier", "humidity")
        )
        assert entity.device_class == SensorDeviceClass.HUMIDITY
        assert entity.native_value == 50.0

    def test_water_level(self, coordinator):
        entity = SberGenericSensor(
            coordinator,
            "device_humidifier_1",
            _spec("hvac_humidifier", "hvac_water_level"),
        )
        assert entity._attr_unique_id == "device_humidifier_1_water_level"
        assert entity.native_value == 75.0
        assert entity._attr_icon == "mdi:water-percent"

    def test_water_percentage(self, coordinator):
        entity = SberGenericSensor(
            coordinator,
            "device_humidifier_1",
            _spec("hvac_humidifier", "hvac_water_percentage"),
        )
        assert entity._attr_unique_id == "device_humidifier_1_water_percentage"
        assert entity.native_value == 80.0
        assert entity._attr_icon == "mdi:water"


class TestHvacSensorMissing:
    def test_missing_temperature_returns_none(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_ac_1"])
        dev["reported_state"] = [
            {"key": "on_off", "bool_value": True},
        ]
        coordinator.data["device_hvac_ac_1"] = dev
        entity = SberGenericSensor(
            coordinator, "device_hvac_ac_1", _spec("hvac_ac", "temperature")
        )
        assert entity.native_value is None


class TestAsyncSetupEntryHvacSensors:
    @pytest.mark.asyncio
    async def test_creates_hvac_sensors(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)

        ids_suffixes = {(e._device_id, e._spec.suffix) for e in entities}
        # hvac_ac → temperature + humidity
        assert ("device_hvac_ac_1", "temperature") in ids_suffixes
        assert ("device_hvac_ac_1", "humidity") in ids_suffixes
        # hvac_heater → temperature
        assert ("device_hvac_heater_1", "temperature") in ids_suffixes
        # hvac_radiator / boiler / underfloor → temperature
        assert ("device_hvac_radiator_1", "temperature") in ids_suffixes
        assert ("device_hvac_boiler_1", "temperature") in ids_suffixes
        assert ("device_hvac_underfloor_1", "temperature") in ids_suffixes
        # humidifier → humidity + water_level + water_percentage
        assert ("device_humidifier_1", "humidity") in ids_suffixes
        assert ("device_humidifier_1", "water_level") in ids_suffixes
        assert ("device_humidifier_1", "water_percentage") in ids_suffixes
        # kettle → water_temperature (already existing)
        assert ("device_kettle_1", "water_temperature") in ids_suffixes
