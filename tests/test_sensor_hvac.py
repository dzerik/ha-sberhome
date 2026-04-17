"""Tests for HVAC sensors (temperature/humidity/water_level) — sbermap-driven (PR #3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass

from custom_components.sberhome.sensor import SberSbermapSensor, async_setup_entry
from tests.conftest import build_coordinator_caches


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.devices, coord.entities = build_coordinator_caches(mock_devices_extra)
    return coord


def _sensor(coordinator, device_id: str, unique_id: str) -> SberSbermapSensor:
    ent = next(
        e for e in coordinator.entities[device_id] if e.unique_id == unique_id
    )
    return SberSbermapSensor(coordinator, device_id, ent)


class TestHvacACCurrentSensors:
    def test_temperature_sensor(self, coordinator):
        e = _sensor(coordinator, "device_hvac_ac_1", "device_hvac_ac_1_temperature")
        assert e._attr_device_class is SensorDeviceClass.TEMPERATURE
        assert e.native_value == 22.5

    def test_humidity_sensor(self, coordinator):
        e = _sensor(coordinator, "device_hvac_ac_1", "device_hvac_ac_1_humidity")
        assert e._attr_device_class is SensorDeviceClass.HUMIDITY
        assert e.native_value == 45  # int(45.0)


class TestHvacHeaterRadiatorBoilerUnderfloor:
    @pytest.mark.parametrize(
        "device_id,expected",
        [
            ("device_hvac_heater_1", 21.0),
            ("device_hvac_radiator_1", 27.0),
            ("device_hvac_boiler_1", 55.0),
            ("device_hvac_underfloor_1", 30.0),
        ],
    )
    def test_temperature(self, coordinator, device_id, expected):
        e = _sensor(coordinator, device_id, f"{device_id}_temperature")
        assert e._attr_device_class is SensorDeviceClass.TEMPERATURE
        assert e.native_value == expected


class TestHumidifierSensors:
    def test_water_level(self, coordinator):
        e = _sensor(
            coordinator, "device_humidifier_1", "device_humidifier_1_hvac_water_level"
        )
        assert e.native_value == 75
        assert e._attr_icon == "mdi:water-percent"

    def test_water_percentage(self, coordinator):
        e = _sensor(
            coordinator,
            "device_humidifier_1",
            "device_humidifier_1_hvac_water_percentage",
        )
        assert e.native_value == 80
        assert e._attr_icon == "mdi:water"


class TestAsyncSetupEntryHvacSensors:
    @pytest.mark.asyncio
    async def test_creates_hvac_sensors(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        ids = {e._attr_unique_id for e in captured}
        assert "device_hvac_ac_1_temperature" in ids
        assert "device_hvac_ac_1_humidity" in ids
        assert "device_hvac_heater_1_temperature" in ids
        assert "device_hvac_radiator_1_temperature" in ids
        assert "device_hvac_boiler_1_temperature" in ids
        assert "device_hvac_underfloor_1_temperature" in ids
        assert "device_humidifier_1_hvac_water_level" in ids
        assert "device_humidifier_1_hvac_water_percentage" in ids
        assert "device_kettle_1_kitchen_water_temperature" in ids
