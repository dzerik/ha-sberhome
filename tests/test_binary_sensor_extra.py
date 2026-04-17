"""Tests for extra binary sensors — sbermap-driven (PR #3 рефакторинга).

Покрывает дополнительные binary_sensor entities (tamper, kitchen_water_low_level,
replace_filter/ionizator, intercom incoming_call) на mock_devices_extra.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.sberhome.binary_sensor import (
    SberSbermapBinarySensor,
    async_setup_entry,
)
from tests.conftest import build_coordinator_caches


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.devices, coord.entities = build_coordinator_caches(mock_devices_extra)
    return coord


def _bs(coordinator, device_id: str, unique_id: str) -> SberSbermapBinarySensor:
    ent = next(
        e for e in coordinator.entities[device_id] if e.unique_id == unique_id
    )
    return SberSbermapBinarySensor(coordinator, device_id, ent)


class TestKettleWaterLowLevel:
    @pytest.fixture
    def water_low(self, coordinator):
        return _bs(coordinator, "device_kettle_1", "device_kettle_1_kitchen_water_low_level")

    def test_unique_id(self, water_low):
        assert water_low._attr_unique_id == "device_kettle_1_kitchen_water_low_level"

    def test_device_class(self, water_low):
        assert water_low._attr_device_class is BinarySensorDeviceClass.PROBLEM

    def test_icon(self, water_low):
        assert water_low._attr_icon == "mdi:water-alert"

    def test_is_on_false(self, water_low):
        assert water_low.is_on is False


class TestHumidifierProblemSensors:
    def test_water_low(self, coordinator):
        e = _bs(coordinator, "device_humidifier_1", "device_humidifier_1_hvac_water_low_level")
        assert e._attr_device_class is BinarySensorDeviceClass.PROBLEM
        assert e.is_on is False

    def test_replace_filter(self, coordinator):
        e = _bs(coordinator, "device_humidifier_1", "device_humidifier_1_hvac_replace_filter")
        assert e._attr_device_class is BinarySensorDeviceClass.PROBLEM
        assert e._attr_entity_category is EntityCategory.DIAGNOSTIC
        assert e._attr_icon == "mdi:air-filter"

    def test_replace_ionizator(self, coordinator):
        e = _bs(coordinator, "device_humidifier_1", "device_humidifier_1_hvac_replace_ionizator")
        assert e._attr_device_class is BinarySensorDeviceClass.PROBLEM
        assert e._attr_entity_category is EntityCategory.DIAGNOSTIC
        assert e._attr_icon == "mdi:flash"


class TestAirPurifierProblemSensors:
    def test_replace_filter(self, coordinator):
        e = _bs(coordinator, "device_hvac_purifier_1", "device_hvac_purifier_1_hvac_replace_filter")
        assert e._attr_device_class is BinarySensorDeviceClass.PROBLEM
        assert e._attr_entity_category is EntityCategory.DIAGNOSTIC

    def test_replace_ionizator(self, coordinator):
        e = _bs(coordinator, "device_hvac_purifier_1", "device_hvac_purifier_1_hvac_replace_ionizator")
        assert e._attr_entity_category is EntityCategory.DIAGNOSTIC


class TestIntercomIncomingCall:
    @pytest.fixture
    def call(self, coordinator):
        return _bs(coordinator, "device_intercom_1", "device_intercom_1_incoming_call")

    def test_device_class(self, call):
        assert call._attr_device_class is BinarySensorDeviceClass.OCCUPANCY

    def test_icon(self, call):
        assert call._attr_icon == "mdi:phone-ring"

    def test_unique_id(self, call):
        assert call._attr_unique_id == "device_intercom_1_incoming_call"

    def test_is_on_false(self, call):
        assert call.is_on is False


class TestAsyncSetupEntryExtra:
    @pytest.mark.asyncio
    async def test_creates_all_extra_binary_sensors(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        ids = {e._attr_unique_id for e in captured}

        assert "device_door_sens_1_battery_low" not in ids  # нет в этом mock
        assert "device_kettle_1_kitchen_water_low_level" in ids
        assert "device_humidifier_1_hvac_water_low_level" in ids
        assert "device_humidifier_1_hvac_replace_filter" in ids
        assert "device_humidifier_1_hvac_replace_ionizator" in ids
        assert "device_hvac_purifier_1_hvac_replace_filter" in ids
        assert "device_hvac_purifier_1_hvac_replace_ionizator" in ids
        assert "device_intercom_1_incoming_call" in ids
