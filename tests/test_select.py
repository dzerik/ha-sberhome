"""Tests for the SberHome select platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.sberhome.select import (
    SberGenericSelect,
    _has_attribute,
    async_setup_entry,
)
from custom_components.sberhome.registry import CATEGORY_SELECTS


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def curtain_open_rate(coordinator):
    spec = CATEGORY_SELECTS["curtain"][0]
    return SberGenericSelect(coordinator, "device_curtain_1", spec)


@pytest.fixture
def ac_air_flow(coordinator):
    spec = CATEGORY_SELECTS["hvac_ac"][0]
    return SberGenericSelect(coordinator, "device_hvac_ac_1", spec)


class TestCurtainOpenRate:
    def test_unique_id(self, curtain_open_rate):
        assert curtain_open_rate._attr_unique_id == "device_curtain_1_open_rate"

    def test_options(self, curtain_open_rate):
        assert curtain_open_rate._attr_options == ["auto", "low", "high"]

    def test_entity_category(self, curtain_open_rate):
        assert curtain_open_rate._attr_entity_category == EntityCategory.CONFIG

    def test_icon(self, curtain_open_rate):
        assert curtain_open_rate._attr_icon == "mdi:speedometer"

    def test_current_option(self, curtain_open_rate):
        assert curtain_open_rate.current_option == "auto"

    def test_current_option_unknown_value(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_curtain_1"])
        dev["desired_state"] = [{"key": "open_rate", "enum_value": "turbo"}]
        coordinator.data["device_curtain_1"] = dev
        spec = CATEGORY_SELECTS["curtain"][0]
        entity = SberGenericSelect(coordinator, "device_curtain_1", spec)
        assert entity.current_option is None

    def test_current_option_missing(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_curtain_1"])
        dev["desired_state"] = []
        coordinator.data["device_curtain_1"] = dev
        spec = CATEGORY_SELECTS["curtain"][0]
        entity = SberGenericSelect(coordinator, "device_curtain_1", spec)
        assert entity.current_option is None

    @pytest.mark.asyncio
    async def test_select_option(self, curtain_open_rate, coordinator):
        await curtain_open_rate.async_select_option("high")
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_curtain_1", [{"key": "open_rate", "enum_value": "high"}]
        )
        coordinator.async_set_updated_data.assert_called_once()


class TestACAirFlowDirection:
    def test_options(self, ac_air_flow):
        assert ac_air_flow._attr_options == ["auto", "top", "middle", "bottom"]

    def test_current_option(self, ac_air_flow):
        assert ac_air_flow.current_option == "top"


class TestHasAttributeFilter:
    def test_has_attribute_true(self, mock_devices_extra):
        assert _has_attribute(mock_devices_extra["device_curtain_1"], "open_rate") is True

    def test_has_attribute_false(self, mock_devices_extra):
        assert _has_attribute(mock_devices_extra["device_curtain_1"], "nonexistent") is False

    def test_has_attribute_no_attributes_key(self):
        """Без секций attributes/reported/desired → False (не создавать ghost entity)."""
        assert _has_attribute({}, "anything") is False


def _sel(category: str, key: str):
    for s in CATEGORY_SELECTS[category]:
        if s.key == key:
            return s
    raise KeyError(f"{category}/{key}")


class TestThermostatModeHeater:
    """hvac_heater → hvac_thermostat_mode (auto/eco/comfort/boost)."""

    @pytest.fixture
    def mode(self, coordinator):
        return SberGenericSelect(
            coordinator, "device_hvac_heater_1", _sel("hvac_heater", "hvac_thermostat_mode")
        )

    def test_unique_id(self, mode):
        assert mode._attr_unique_id == "device_hvac_heater_1_thermostat_mode"

    def test_options(self, mode):
        assert mode._attr_options == ["auto", "eco", "comfort", "boost"]

    def test_current_option(self, mode):
        assert mode.current_option == "auto"

    def test_icon(self, mode):
        assert mode._attr_icon == "mdi:thermostat"

    @pytest.mark.asyncio
    async def test_select_option(self, mode, coordinator):
        await mode.async_select_option("comfort")
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_heater_1",
            [{"key": "hvac_thermostat_mode", "enum_value": "comfort"}],
        )


class TestBoilerThermostatAndRate:
    """hvac_boiler → thermostat_mode + heating_rate."""

    def test_thermostat_mode_current(self, coordinator):
        entity = SberGenericSelect(
            coordinator,
            "device_hvac_boiler_1",
            _sel("hvac_boiler", "hvac_thermostat_mode"),
        )
        assert entity.current_option == "comfort"

    def test_heating_rate(self, coordinator):
        spec = _sel("hvac_boiler", "hvac_heating_rate")
        entity = SberGenericSelect(coordinator, "device_hvac_boiler_1", spec)
        assert entity._attr_unique_id == "device_hvac_boiler_1_heating_rate"
        assert entity._attr_options == ["slow", "medium", "fast"]
        assert entity.current_option == "medium"
        assert entity._attr_entity_category == EntityCategory.CONFIG
        assert entity._attr_icon == "mdi:speedometer"


class TestUnderfloorSelects:
    """hvac_underfloor_heating → thermostat_mode + heating_rate."""

    def test_thermostat_mode(self, coordinator):
        entity = SberGenericSelect(
            coordinator,
            "device_hvac_underfloor_1",
            _sel("hvac_underfloor_heating", "hvac_thermostat_mode"),
        )
        assert entity.current_option == "eco"

    def test_heating_rate(self, coordinator):
        entity = SberGenericSelect(
            coordinator,
            "device_hvac_underfloor_1",
            _sel("hvac_underfloor_heating", "hvac_heating_rate"),
        )
        assert entity.current_option == "slow"


class TestFanDirection:
    """hvac_fan → hvac_direction_set (auto/top/middle/bottom/swing)."""

    def test_options(self, coordinator):
        spec = _sel("hvac_fan", "hvac_direction_set")
        entity = SberGenericSelect(coordinator, "device_hvac_fan_1", spec)
        assert entity._attr_options == ["auto", "top", "middle", "bottom", "swing"]

    def test_icon(self, coordinator):
        spec = _sel("hvac_fan", "hvac_direction_set")
        entity = SberGenericSelect(coordinator, "device_hvac_fan_1", spec)
        assert entity._attr_icon == "mdi:arrow-decision"


class TestSensorSensitive:
    """sensor_door, sensor_pir, sensor_gas → sensor_sensitive (auto/high)."""

    @pytest.mark.parametrize(
        "device_id,category",
        [
            ("device_door_sens_1", "sensor_door"),
            ("device_pir_sens_1", "sensor_pir"),
            ("device_gas_1", "sensor_gas"),
        ],
    )
    def test_sensor_sensitive_options(self, coordinator, device_id, category):
        spec = _sel(category, "sensor_sensitive")
        entity = SberGenericSelect(coordinator, device_id, spec)
        assert entity._attr_options == ["auto", "high"]
        assert entity._attr_entity_category == EntityCategory.CONFIG

    def test_door_sensor_current(self, coordinator):
        spec = _sel("sensor_door", "sensor_sensitive")
        entity = SberGenericSelect(coordinator, "device_door_sens_1", spec)
        # fixture desired_state: sensor_sensitive=high
        assert entity.current_option == "high"

    def test_pir_sensor_current(self, coordinator):
        spec = _sel("sensor_pir", "sensor_sensitive")
        entity = SberGenericSelect(coordinator, "device_pir_sens_1", spec)
        assert entity.current_option == "auto"


class TestVacuumCleaningType:
    """vacuum_cleaner → vacuum_cleaner_cleaning_type (dry/wet/mixed)."""

    def test_options(self, coordinator):
        spec = _sel("vacuum_cleaner", "vacuum_cleaner_cleaning_type")
        entity = SberGenericSelect(coordinator, "device_vacuum_1", spec)
        assert entity._attr_options == ["dry", "wet", "mixed"]
        assert entity._attr_icon == "mdi:broom"
        assert entity._attr_unique_id == "device_vacuum_1_cleaning_type"


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_select_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        ids = [(e._device_id, e._spec.key) for e in entities]
        # curtain → open_rate (has attr)
        assert ("device_curtain_1", "open_rate") in ids
        # gate has no attribute entry → not created
        assert ("device_gate_1", "open_rate") not in ids
        # hvac_ac → hvac_air_flow_direction (has attr)
        assert ("device_hvac_ac_1", "hvac_air_flow_direction") in ids
        # vacuum → program (has attr)
        assert ("device_vacuum_1", "vacuum_cleaner_program") in ids
        # thermostat_mode/heating_rate for boiler/underfloor
        assert ("device_hvac_boiler_1", "hvac_thermostat_mode") in ids
        assert ("device_hvac_boiler_1", "hvac_heating_rate") in ids
        assert ("device_hvac_underfloor_1", "hvac_thermostat_mode") in ids
        assert ("device_hvac_underfloor_1", "hvac_heating_rate") in ids
        # heater thermostat_mode
        assert ("device_hvac_heater_1", "hvac_thermostat_mode") in ids
        # sensor_sensitive
        assert ("device_door_sens_1", "sensor_sensitive") in ids
        assert ("device_pir_sens_1", "sensor_sensitive") in ids
        assert ("device_gas_1", "sensor_sensitive") in ids

    @pytest.mark.asyncio
    async def test_no_selects_for_unrelated_devices(self, mock_devices):
        coordinator = MagicMock()
        coordinator.data = mock_devices
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # sensor_temp in mock_devices has selects but no 'attributes' with keys
        # → filter prevents creation (attributes==[] but no matching key → False)
        # Actually _has_attribute returns False when attributes present but key missing.
        # climate sensor has attributes=[] → no selects created
        for e in entities:
            assert e._device_id != "device_climate_1"
