"""Tests for SberHome extra binary sensors (tamper, water_low, filter, intercom)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.sberhome.binary_sensor import (
    SberGenericBinarySensor,
    async_setup_entry,
)
from custom_components.sberhome.registry import (
    CATEGORY_BINARY_SENSORS,
    BinarySensorSpec,
)


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


def _find_spec(category: str, key: str) -> BinarySensorSpec:
    for s in CATEGORY_BINARY_SENSORS[category]:
        if s.key == key:
            return s
    raise KeyError(f"{category}/{key}")


class TestDoorTamperAlarm:
    """sensor_door → tamper_alarm (TAMPER, DIAGNOSTIC)."""

    @pytest.fixture
    def tamper(self, coordinator):
        spec = _find_spec("sensor_door", "tamper_alarm")
        # Fixture для door в mock_devices_extra — door_sens_1. Используем его.
        return SberGenericBinarySensor(coordinator, "device_door_sens_1", spec)

    def test_unique_id(self, tamper):
        assert tamper._attr_unique_id == "device_door_sens_1_tamper"

    def test_device_class(self, tamper):
        assert tamper.device_class == BinarySensorDeviceClass.TAMPER

    def test_entity_category_diagnostic(self, tamper):
        assert tamper._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_is_on_no_reported_state(self, tamper):
        """fixture has no tamper_alarm in reported_state → None."""
        assert tamper.is_on is None

    def test_is_on_true(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_door_sens_1"])
        dev["reported_state"] = [
            {"key": "tamper_alarm", "bool_value": True},
        ]
        coordinator.data["device_door_sens_1"] = dev
        spec = _find_spec("sensor_door", "tamper_alarm")
        entity = SberGenericBinarySensor(coordinator, "device_door_sens_1", spec)
        assert entity.is_on is True


class TestKettleWaterLowLevel:
    """kettle → kitchen_water_low_level (PROBLEM)."""

    @pytest.fixture
    def water_low(self, coordinator):
        spec = _find_spec("kettle", "kitchen_water_low_level")
        return SberGenericBinarySensor(coordinator, "device_kettle_1", spec)

    def test_unique_id(self, water_low):
        assert water_low._attr_unique_id == "device_kettle_1_water_low_level"

    def test_device_class(self, water_low):
        assert water_low.device_class == BinarySensorDeviceClass.PROBLEM

    def test_icon(self, water_low):
        assert water_low._attr_icon == "mdi:water-alert"

    def test_is_on_false(self, water_low):
        assert water_low.is_on is False

    def test_is_on_true(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_kettle_1"])
        dev["reported_state"] = [
            {"key": "kitchen_water_low_level", "bool_value": True},
        ]
        coordinator.data["device_kettle_1"] = dev
        spec = _find_spec("kettle", "kitchen_water_low_level")
        entity = SberGenericBinarySensor(coordinator, "device_kettle_1", spec)
        assert entity.is_on is True


class TestHumidifierProblemSensors:
    """hvac_humidifier → water_low_level, replace_filter (DIAGNOSTIC), replace_ionizator (DIAGNOSTIC)."""

    def test_water_low(self, coordinator):
        spec = _find_spec("hvac_humidifier", "hvac_water_low_level")
        entity = SberGenericBinarySensor(coordinator, "device_humidifier_1", spec)
        assert entity.device_class == BinarySensorDeviceClass.PROBLEM
        assert entity._attr_unique_id == "device_humidifier_1_water_low_level"
        assert entity.is_on is False

    def test_replace_filter(self, coordinator):
        spec = _find_spec("hvac_humidifier", "hvac_replace_filter")
        entity = SberGenericBinarySensor(coordinator, "device_humidifier_1", spec)
        assert entity.device_class == BinarySensorDeviceClass.PROBLEM
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
        assert entity._attr_icon == "mdi:air-filter"
        assert entity.is_on is False

    def test_replace_ionizator(self, coordinator):
        spec = _find_spec("hvac_humidifier", "hvac_replace_ionizator")
        entity = SberGenericBinarySensor(coordinator, "device_humidifier_1", spec)
        assert entity.device_class == BinarySensorDeviceClass.PROBLEM
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
        assert entity._attr_icon == "mdi:flash"


class TestAirPurifierProblemSensors:
    """hvac_air_purifier → replace_filter (DIAGNOSTIC), replace_ionizator (DIAGNOSTIC)."""

    def test_replace_filter(self, coordinator):
        spec = _find_spec("hvac_air_purifier", "hvac_replace_filter")
        entity = SberGenericBinarySensor(coordinator, "device_hvac_purifier_1", spec)
        assert entity.device_class == BinarySensorDeviceClass.PROBLEM
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC
        assert entity.is_on is False

    def test_replace_ionizator(self, coordinator):
        spec = _find_spec("hvac_air_purifier", "hvac_replace_ionizator")
        entity = SberGenericBinarySensor(coordinator, "device_hvac_purifier_1", spec)
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC


class TestIntercomIncomingCall:
    """intercom → incoming_call (OCCUPANCY)."""

    @pytest.fixture
    def call(self, coordinator):
        spec = _find_spec("intercom", "incoming_call")
        return SberGenericBinarySensor(coordinator, "device_intercom_1", spec)

    def test_device_class(self, call):
        assert call.device_class == BinarySensorDeviceClass.OCCUPANCY

    def test_icon(self, call):
        assert call._attr_icon == "mdi:phone-ring"

    def test_unique_id(self, call):
        assert call._attr_unique_id == "device_intercom_1_incoming_call"

    def test_is_on_false(self, call):
        assert call.is_on is False

    def test_is_on_true(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_intercom_1"])
        dev["reported_state"] = [
            {"key": "online", "bool_value": True},
            {"key": "incoming_call", "bool_value": True},
        ]
        coordinator.data["device_intercom_1"] = dev
        spec = _find_spec("intercom", "incoming_call")
        entity = SberGenericBinarySensor(coordinator, "device_intercom_1", spec)
        assert entity.is_on is True


class TestAsyncSetupEntryExtra:
    @pytest.mark.asyncio
    async def test_creates_all_extra_binary_sensors(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)

        # Check that our new sensors are created
        ids_suffixes = {(e._device_id, e._spec.suffix) for e in entities}

        # Door sensors → doorcontact + tamper (no battery_low_power in this fixture)
        assert ("device_door_sens_1", "") in ids_suffixes
        assert ("device_door_sens_1", "tamper") in ids_suffixes
        # Kettle → water_low_level
        assert ("device_kettle_1", "water_low_level") in ids_suffixes
        # Humidifier → 3 sensors
        assert ("device_humidifier_1", "water_low_level") in ids_suffixes
        assert ("device_humidifier_1", "replace_filter") in ids_suffixes
        assert ("device_humidifier_1", "replace_ionizator") in ids_suffixes
        # Air purifier
        assert ("device_hvac_purifier_1", "replace_filter") in ids_suffixes
        assert ("device_hvac_purifier_1", "replace_ionizator") in ids_suffixes
        # Intercom → incoming_call + online (connectivity)
        assert ("device_intercom_1", "incoming_call") in ids_suffixes
        assert ("device_intercom_1", "connectivity") in ids_suffixes
        # Gas / smoke → their state sensors
        assert ("device_gas_1", "") in ids_suffixes
        assert ("device_smoke_1", "") in ids_suffixes
