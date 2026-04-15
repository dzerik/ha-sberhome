"""Tests for the SberHome sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.sberhome.sensor import (
    SberBatterySensor,
    SberCurrentSensor,
    SberHumiditySensor,
    SberPowerSensor,
    SberSignalStrengthSensor,
    SberTemperatureSensor,
    SberVoltageSensor,
    async_setup_entry,
)
from tests.conftest import (
    MOCK_DEVICE_CLIMATE_SENSOR,
    MOCK_DEVICE_DOOR_SENSOR,
    MOCK_DEVICE_SWITCH,
    MOCK_DEVICE_WATER_LEAK,
)


class TestSberTemperatureSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberTemperatureSensor(coordinator, "device_climate_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_climate_1_temperature"

    def test_name(self, entity):
        assert entity._attr_name == "Temperature"

    def test_native_value(self, entity):
        assert entity.native_value == 23.5

    def test_native_value_missing(self, coordinator):
        coordinator.data["device_climate_1"] = {
            **MOCK_DEVICE_CLIMATE_SENSOR,
            "reported_state": [],
        }
        entity = SberTemperatureSensor(coordinator, "device_climate_1")
        assert entity.native_value is None

    def test_device_info(self, entity):
        info = entity.device_info
        assert info["serial_number"] == "SN_CLIMATE_001"
        assert info["manufacturer"] == "Sber"

    def test_suggested_display_precision(self, entity):
        assert entity._attr_suggested_display_precision == 1


class TestSberHumiditySensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberHumiditySensor(coordinator, "device_climate_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_climate_1_humidity"

    def test_native_value(self, entity):
        assert entity.native_value == 45.2

    def test_native_value_no_reported_state(self, coordinator):
        coordinator.data["device_climate_1"] = {
            **MOCK_DEVICE_CLIMATE_SENSOR,
        }
        del coordinator.data["device_climate_1"]["reported_state"]
        entity = SberHumiditySensor(coordinator, "device_climate_1")
        assert entity.native_value is None

    def test_suggested_display_precision(self, entity):
        assert entity._attr_suggested_display_precision == 0


class TestSberBatterySensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberBatterySensor(coordinator, "device_climate_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_climate_1_battery"

    def test_native_value(self, entity):
        assert entity.native_value == 87

    def test_entity_category_diagnostic(self, entity):
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC


class TestSberSignalStrengthSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberSignalStrengthSensor(coordinator, "device_door_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_door_1_signal_strength"

    def test_native_value(self, entity):
        assert entity.native_value == -40

    def test_entity_category_diagnostic(self, entity):
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_native_value_no_reported_state(self, coordinator):
        coordinator.data["device_door_1"] = {
            **MOCK_DEVICE_DOOR_SENSOR,
            "reported_state": [],
        }
        entity = SberSignalStrengthSensor(coordinator, "device_door_1")
        assert entity.native_value is None


class TestSberVoltageSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberVoltageSensor(coordinator, "device_switch_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_switch_1_voltage"

    def test_native_value(self, entity):
        assert entity.native_value == 222.5

    def test_native_value_no_reported_state(self, coordinator):
        coordinator.data["device_switch_1"] = {
            **MOCK_DEVICE_SWITCH,
            "reported_state": [],
        }
        entity = SberVoltageSensor(coordinator, "device_switch_1")
        assert entity.native_value is None


class TestSberCurrentSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberCurrentSensor(coordinator, "device_switch_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_switch_1_current"

    def test_native_value_milliamps_to_amps(self, entity):
        assert entity.native_value == 0.15  # 150mA -> 0.15A

    def test_native_value_no_reported_state(self, coordinator):
        coordinator.data["device_switch_1"] = {
            **MOCK_DEVICE_SWITCH,
            "reported_state": [],
        }
        entity = SberCurrentSensor(coordinator, "device_switch_1")
        assert entity.native_value is None


class TestSberPowerSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberPowerSensor(coordinator, "device_switch_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_switch_1_power"

    def test_native_value(self, entity):
        assert entity.native_value == 33.4

    def test_native_value_no_reported_state(self, coordinator):
        coordinator.data["device_switch_1"] = {
            **MOCK_DEVICE_SWITCH,
            "reported_state": [],
        }
        entity = SberPowerSensor(coordinator, "device_switch_1")
        assert entity.native_value is None


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_entities(self, mock_devices):
        coordinator = MagicMock()
        coordinator.data = mock_devices
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []

        def capture(ents):
            entities.extend(ents)

        await async_setup_entry(MagicMock(), entry, capture)

        # climate sensor: temperature + humidity + battery + signal_strength = 4
        # smart plug: voltage + current + power = 3
        # water leak: battery = 1
        # door: battery + signal_strength = 2
        # motion: battery = 1
        assert len(entities) == 11
        from homeassistant.components.sensor import SensorDeviceClass

        device_classes = [e.device_class for e in entities]
        assert device_classes.count(SensorDeviceClass.TEMPERATURE) == 1
        assert device_classes.count(SensorDeviceClass.HUMIDITY) == 1
        assert device_classes.count(SensorDeviceClass.BATTERY) == 4
        assert device_classes.count(SensorDeviceClass.VOLTAGE) == 1
        assert device_classes.count(SensorDeviceClass.CURRENT) == 1
        assert device_classes.count(SensorDeviceClass.POWER) == 1
        assert device_classes.count(SensorDeviceClass.SIGNAL_STRENGTH) == 2
