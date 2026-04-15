"""Tests for the SberHome number platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory, UnitOfTemperature, UnitOfTime

from custom_components.sberhome.number import (
    SberGenericNumber,
    async_setup_entry,
)
from custom_components.sberhome.registry import CATEGORY_NUMBERS, NumberSpec


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def kettle_number(coordinator):
    spec = CATEGORY_NUMBERS["kettle"][0]
    return SberGenericNumber(coordinator, "device_kettle_1", spec)


class TestKettleTargetTemperature:
    def test_unique_id(self, kettle_number):
        assert kettle_number._attr_unique_id == "device_kettle_1_target_temperature"

    def test_name(self, kettle_number):
        assert kettle_number._attr_name == "Target Temperature"

    def test_unit(self, kettle_number):
        assert kettle_number._attr_native_unit_of_measurement == UnitOfTemperature.CELSIUS

    def test_min_max_step(self, kettle_number):
        assert kettle_number._attr_native_min_value == 60
        assert kettle_number._attr_native_max_value == 100
        assert kettle_number._attr_native_step == 10

    def test_icon(self, kettle_number):
        assert kettle_number._attr_icon == "mdi:thermometer"

    def test_native_value(self, kettle_number):
        assert kettle_number.native_value == 80.0

    def test_native_value_missing(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_kettle_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": False}]
        coordinator.data["device_kettle_1"] = dev
        entity = SberGenericNumber(
            coordinator, "device_kettle_1", CATEGORY_NUMBERS["kettle"][0]
        )
        assert entity.native_value is None

    def test_native_value_float(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_kettle_1"])
        dev["desired_state"] = [
            {"key": "kitchen_water_temperature_set", "float_value": 72.5}
        ]
        coordinator.data["device_kettle_1"] = dev
        entity = SberGenericNumber(
            coordinator, "device_kettle_1", CATEGORY_NUMBERS["kettle"][0]
        )
        assert entity.native_value == 72.5

    @pytest.mark.asyncio
    async def test_set_native_value(self, kettle_number, coordinator):
        await kettle_number.async_set_native_value(90)
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_kettle_1",
            [{"key": "kitchen_water_temperature_set", "integer_value": 90}],
        )
        coordinator.async_set_updated_data.assert_called_once()


class TestScaleHandling:
    """NumberSpec.scale: raw_value * scale = domain value."""

    def test_scale_read(self, coordinator, mock_devices_extra):
        spec = NumberSpec(
            "kitchen_water_temperature_set",
            "scaled",
            scale=0.1,
        )
        entity = SberGenericNumber(coordinator, "device_kettle_1", spec)
        # raw 80 * 0.1 = 8.0
        assert entity.native_value == pytest.approx(8.0)

    @pytest.mark.asyncio
    async def test_scale_write(self, coordinator, mock_devices_extra):
        spec = NumberSpec("some_key", "scaled", scale=0.1)
        entity = SberGenericNumber(coordinator, "device_kettle_1", spec)
        await entity.async_set_native_value(8.0)
        # 8.0 / 0.1 = 80
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_kettle_1", [{"key": "some_key", "integer_value": 80}]
        )


class TestLedStripSleepTimer:
    def test_entity_category(self, coordinator, mock_devices_extra):
        coordinator.data["device_ledstrip_sleep_1"] = {
            "id": "device_ledstrip_sleep_1",
            "serial_number": "SN_LS_SLEEP",
            "name": {"name": "LED Sleep"},
            "image_set_type": "ledstrip_sber",
            "sw_version": "1",
            "device_info": {"manufacturer": "Sber", "model": "SBDV-LEDSTRIP"},
            "desired_state": [{"key": "sleep_timer", "integer_value": 60}],
            "reported_state": [],
            "attributes": [],
        }
        spec = CATEGORY_NUMBERS["led_strip"][0]
        entity = SberGenericNumber(coordinator, "device_ledstrip_sleep_1", spec)
        assert entity._attr_entity_category == EntityCategory.CONFIG
        assert entity._attr_native_unit_of_measurement == UnitOfTime.MINUTES
        assert entity.native_value == 60


class TestAcHumidityTarget:
    """hvac_ac → hvac_humidity_set (30-80% step 5)."""

    @pytest.fixture
    def humidity(self, coordinator):
        spec = CATEGORY_NUMBERS["hvac_ac"][0]
        return SberGenericNumber(coordinator, "device_hvac_ac_1", spec)

    def test_unique_id(self, humidity):
        assert humidity._attr_unique_id == "device_hvac_ac_1_target_humidity"

    def test_unit_is_percentage(self, humidity):
        from homeassistant.const import PERCENTAGE

        assert humidity._attr_native_unit_of_measurement == PERCENTAGE

    def test_range(self, humidity):
        assert humidity._attr_native_min_value == 30
        assert humidity._attr_native_max_value == 80
        assert humidity._attr_native_step == 5

    def test_icon(self, humidity):
        assert humidity._attr_icon == "mdi:water-percent"

    def test_native_value(self, humidity):
        assert humidity.native_value == 50

    @pytest.mark.asyncio
    async def test_set_value(self, humidity, coordinator):
        await humidity.async_set_native_value(65)
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1", [{"key": "hvac_humidity_set", "integer_value": 65}]
        )


class TestWindowBlindLightTransmission:
    """window_blind → light_transmission_percentage (0-100% step 1)."""

    @pytest.fixture
    def light(self, coordinator):
        spec = CATEGORY_NUMBERS["window_blind"][0]
        return SberGenericNumber(coordinator, "device_blind_1", spec)

    def test_unique_id(self, light):
        assert light._attr_unique_id == "device_blind_1_light_transmission"

    def test_range(self, light):
        assert light._attr_native_min_value == 0
        assert light._attr_native_max_value == 100
        assert light._attr_native_step == 1

    def test_icon(self, light):
        assert light._attr_icon == "mdi:weather-sunny"

    def test_native_value(self, light):
        assert light.native_value == 60


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_number_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # kettle (target temp) + hvac_ac (hvac_humidity_set) + window_blind (light_transmission) = 3
        assert len(entities) == 3
        device_ids = [e._device_id for e in entities]
        assert "device_kettle_1" in device_ids
        assert "device_hvac_ac_1" in device_ids
        assert "device_blind_1" in device_ids
