"""Tests for the SberHome binary sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.sberhome.binary_sensor import (
    SberBatteryLowSensor,
    SberDoorSensor,
    SberMotionSensor,
    SberWaterLeakSensor,
    async_setup_entry,
)
from tests.conftest import (
    MOCK_DEVICE_DOOR_SENSOR,
    MOCK_DEVICE_MOTION_SENSOR,
    MOCK_DEVICE_WATER_LEAK,
)


class TestSberWaterLeakSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberWaterLeakSensor(coordinator, "device_water_leak_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_water_leak_1"

    def test_name(self, entity):
        assert entity._attr_name is None  # primary entity inherits device name

    def test_device_class(self, entity):
        assert entity.device_class == BinarySensorDeviceClass.MOISTURE

    def test_is_on_false(self, entity):
        assert entity.is_on is False

    def test_is_on_true(self, coordinator):
        coordinator.data["device_water_leak_1"] = {
            **MOCK_DEVICE_WATER_LEAK,
            "reported_state": [
                {"key": "water_leak_state", "type": "BOOL", "bool_value": True},
            ],
        }
        entity = SberWaterLeakSensor(coordinator, "device_water_leak_1")
        assert entity.is_on is True

    def test_device_info(self, entity):
        info = entity.device_info
        assert info["serial_number"] == "SN_WATER_001"


class TestSberDoorSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberDoorSensor(coordinator, "device_door_1")

    def test_device_class(self, entity):
        assert entity.device_class == BinarySensorDeviceClass.DOOR

    def test_is_on(self, entity):
        assert entity.is_on is True

    def test_is_on_no_reported_state(self, coordinator):
        coordinator.data["device_door_1"] = {
            **MOCK_DEVICE_DOOR_SENSOR,
        }
        del coordinator.data["device_door_1"]["reported_state"]
        entity = SberDoorSensor(coordinator, "device_door_1")
        assert entity.is_on is None


class TestSberMotionSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberMotionSensor(coordinator, "device_motion_1")

    def test_device_class(self, entity):
        assert entity.device_class == BinarySensorDeviceClass.MOTION

    def test_is_on(self, entity):
        assert entity.is_on is False


class TestSberBatteryLowSensor:
    @pytest.fixture
    def coordinator(self, mock_devices):
        coord = MagicMock()
        coord.data = mock_devices
        return coord

    @pytest.fixture
    def entity(self, coordinator):
        return SberBatteryLowSensor(coordinator, "device_water_leak_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_water_leak_1_battery_low"

    def test_device_class(self, entity):
        assert entity.device_class == BinarySensorDeviceClass.BATTERY

    def test_entity_category_diagnostic(self, entity):
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_is_on_false(self, entity):
        assert entity.is_on is False

    def test_is_on_true(self, coordinator):
        coordinator.data["device_water_leak_1"] = {
            **MOCK_DEVICE_WATER_LEAK,
            "reported_state": [
                {"key": "battery_low_power", "type": "BOOL", "bool_value": True},
            ],
        }
        entity = SberBatteryLowSensor(coordinator, "device_water_leak_1")
        assert entity.is_on is True

    def test_is_on_no_reported_state(self, coordinator):
        coordinator.data["device_water_leak_1"] = {
            **MOCK_DEVICE_WATER_LEAK,
        }
        del coordinator.data["device_water_leak_1"]["reported_state"]
        entity = SberBatteryLowSensor(coordinator, "device_water_leak_1")
        assert entity.is_on is None


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

        # water leak + battery_low = 2
        # door + battery_low + tamper = 3
        # motion (no battery_low_power) = 1
        assert len(entities) == 6
        device_classes = [e.device_class for e in entities]
        assert device_classes.count(BinarySensorDeviceClass.MOISTURE) == 1
        assert device_classes.count(BinarySensorDeviceClass.DOOR) == 1
        assert device_classes.count(BinarySensorDeviceClass.MOTION) == 1
        assert device_classes.count(BinarySensorDeviceClass.BATTERY) == 2
        assert device_classes.count(BinarySensorDeviceClass.TAMPER) == 1
