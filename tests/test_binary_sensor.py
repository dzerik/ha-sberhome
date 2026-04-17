"""Tests for the SberHome binary sensor platform — sbermap-driven (PR #3)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.sberhome.binary_sensor import (
    SberSbermapBinarySensor,
    async_setup_entry,
)


def _bs_by_id(coordinator, device_id: str, unique_id: str) -> SberSbermapBinarySensor:
    ent = next(
        e for e in coordinator.entities[device_id] if e.unique_id == unique_id
    )
    return SberSbermapBinarySensor(coordinator, device_id, ent)


class TestWaterLeakSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _bs_by_id(
            mock_coordinator_with_entities, "device_water_leak_1", "device_water_leak_1"
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_water_leak_1"

    def test_name(self, entity):
        assert entity._attr_name is None  # primary entity

    def test_device_class(self, entity):
        assert entity._attr_device_class is BinarySensorDeviceClass.MOISTURE

    def test_is_on_false(self, entity):
        assert entity.is_on is False


class TestDoorSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _bs_by_id(
            mock_coordinator_with_entities, "device_door_1", "device_door_1"
        )

    def test_device_class(self, entity):
        assert entity._attr_device_class is BinarySensorDeviceClass.DOOR

    def test_is_on(self, entity):
        assert entity.is_on is True

    def test_is_on_when_entity_missing(self, entity, mock_coordinator_with_entities):
        mock_coordinator_with_entities.entities["device_door_1"] = []
        assert entity.is_on is None


class TestMotionSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _bs_by_id(
            mock_coordinator_with_entities, "device_motion_1", "device_motion_1"
        )

    def test_device_class(self, entity):
        assert entity._attr_device_class is BinarySensorDeviceClass.MOTION

    def test_is_on(self, entity):
        assert entity.is_on is False


class TestBatteryLowSensor:
    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _bs_by_id(
            mock_coordinator_with_entities,
            "device_water_leak_1",
            "device_water_leak_1_battery_low_power",
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_water_leak_1_battery_low_power"

    def test_device_class(self, entity):
        assert entity._attr_device_class is BinarySensorDeviceClass.BATTERY

    def test_entity_category_diagnostic(self, entity):
        assert entity._attr_entity_category is EntityCategory.DIAGNOSTIC

    def test_is_on_false(self, entity):
        assert entity.is_on is False


class TestTamperSensor:
    """Door sensor mock содержит tamper_alarm — проверяем что entity создаётся."""

    @pytest.fixture
    def entity(self, mock_coordinator_with_entities):
        return _bs_by_id(
            mock_coordinator_with_entities,
            "device_door_1",
            "device_door_1_tamper_alarm",
        )

    def test_device_class(self, entity):
        assert entity._attr_device_class is BinarySensorDeviceClass.TAMPER

    def test_entity_category_diagnostic(self, entity):
        assert entity._attr_entity_category is EntityCategory.DIAGNOSTIC


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_entities(self, mock_coordinator_with_entities):
        entry = MagicMock()
        entry.runtime_data = mock_coordinator_with_entities
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        device_classes = [e._attr_device_class for e in captured]
        # water leak + battery_low = 2
        # door + battery_low + tamper = 3
        # motion = 1 (battery_low отсутствует в mock)
        assert device_classes.count(BinarySensorDeviceClass.MOISTURE) == 1
        assert device_classes.count(BinarySensorDeviceClass.DOOR) == 1
        assert device_classes.count(BinarySensorDeviceClass.MOTION) == 1
        assert device_classes.count(BinarySensorDeviceClass.BATTERY) == 2
        assert device_classes.count(BinarySensorDeviceClass.TAMPER) == 1
