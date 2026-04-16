"""Tests for the SberHome sensor platform — sbermap-driven (PR #3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.sberhome.sensor import SberSbermapSensor, async_setup_entry


def _sensor_by_id(coordinator, device_id: str, unique_id: str) -> SberSbermapSensor:
    """Helper: построить SberSbermapSensor для конкретного unique_id из entities."""
    ent = next(
        e for e in coordinator.entities[device_id] if e.unique_id == unique_id
    )
    return SberSbermapSensor(coordinator, device_id, ent)


class TestTemperatureSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _sensor_by_id(
            mock_coordinator_with_entities,
            "device_climate_1",
            "device_climate_1_temperature",
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_climate_1_temperature"

    def test_native_value(self, entity):
        assert entity.native_value == 23.5

    def test_device_class(self, entity):
        assert entity._attr_device_class is SensorDeviceClass.TEMPERATURE

    def test_suggested_display_precision(self, entity):
        assert entity._attr_suggested_display_precision == 1


class TestHumiditySensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _sensor_by_id(
            mock_coordinator_with_entities,
            "device_climate_1",
            "device_climate_1_humidity",
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_climate_1_humidity"

    def test_native_value(self, entity):
        assert entity.native_value == 45  # int(45.2)

    def test_device_class(self, entity):
        assert entity._attr_device_class is SensorDeviceClass.HUMIDITY


class TestBatterySensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _sensor_by_id(
            mock_coordinator_with_entities,
            "device_climate_1",
            "device_climate_1_battery",
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_climate_1_battery"

    def test_native_value(self, entity):
        assert entity.native_value == 87

    def test_entity_category_diagnostic(self, entity):
        assert entity._attr_entity_category is EntityCategory.DIAGNOSTIC


class TestSignalStrengthSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _sensor_by_id(
            mock_coordinator_with_entities,
            "device_door_1",
            "device_door_1_signal_strength",
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_door_1_signal_strength"

    def test_native_value(self, entity):
        assert entity.native_value == -40

    def test_entity_category_diagnostic(self, entity):
        assert entity._attr_entity_category is EntityCategory.DIAGNOSTIC


class TestVoltageSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _sensor_by_id(
            mock_coordinator_with_entities,
            "device_switch_1",
            "device_switch_1_voltage",
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_switch_1_voltage"

    def test_native_value(self, entity):
        # Sber wire: INTEGER в Volts напрямую (PR #10).
        assert entity.native_value == 222


class TestCurrentSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _sensor_by_id(
            mock_coordinator_with_entities,
            "device_switch_1",
            "device_switch_1_current",
        )

    def test_native_value(self, entity):
        # Sber wire: INTEGER в Amperes напрямую (НЕ mA, как раньше думали).
        # Подтверждено через MQTT-SberGate (PR #10).
        assert entity.native_value == 1


class TestPowerSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _sensor_by_id(
            mock_coordinator_with_entities,
            "device_switch_1",
            "device_switch_1_power",
        )

    def test_native_value(self, entity):
        # Sber wire: INTEGER в Watts напрямую (PR #10).
        assert entity.native_value == 33


class TestNativeValueMissing:
    def test_returns_none_when_entity_disappears(
        self, mock_coordinator_with_entities
    ):
        ent = _sensor_by_id(
            mock_coordinator_with_entities,
            "device_climate_1",
            "device_climate_1_temperature",
        )
        # Стереть из entities — sensor должен вернуть None.
        mock_coordinator_with_entities.entities["device_climate_1"] = []
        assert ent.native_value is None


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_entities(self, mock_coordinator_with_entities):
        entry = MagicMock()
        entry.runtime_data = mock_coordinator_with_entities
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        # climate sensor: temp + humidity + battery + signal = 4
        # smart plug: voltage + current + power = 3
        # water leak: battery = 1
        # door: battery + signal_strength + tamper(no — value None) → battery+signal=2
        # motion: battery = 1
        # ledstrip: 0 (no reported sensors in mock)
        # bulb: 0 (no reported sensors in mock)
        device_classes = [e._attr_device_class for e in captured]
        assert device_classes.count(SensorDeviceClass.TEMPERATURE) == 1
        assert device_classes.count(SensorDeviceClass.HUMIDITY) == 1
        assert device_classes.count(SensorDeviceClass.BATTERY) == 4
        assert device_classes.count(SensorDeviceClass.VOLTAGE) == 1
        assert device_classes.count(SensorDeviceClass.CURRENT) == 1
        assert device_classes.count(SensorDeviceClass.POWER) == 1
        assert device_classes.count(SensorDeviceClass.SIGNAL_STRENGTH) == 2
