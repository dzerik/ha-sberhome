"""Tests for the SberHome climate platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)

from custom_components.sberhome.climate import (
    HA_TO_SBER_HVAC,
    SBER_TO_HA_HVAC,
    SberGenericClimate,
    async_setup_entry,
)
from custom_components.sberhome.registry import CATEGORY_CLIMATE


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def ac_entity(coordinator):
    return SberGenericClimate(coordinator, "device_hvac_ac_1", CATEGORY_CLIMATE["hvac_ac"])


@pytest.fixture
def heater_entity(coordinator):
    return SberGenericClimate(coordinator, "device_hvac_heater_1", CATEGORY_CLIMATE["hvac_heater"])


class TestSberClimateAC:
    def test_unique_id(self, ac_entity):
        assert ac_entity._attr_unique_id == "device_hvac_ac_1"

    def test_name(self, ac_entity):
        assert ac_entity._attr_name is None

    def test_min_max_temp(self, ac_entity):
        assert ac_entity._attr_min_temp == 16
        assert ac_entity._attr_max_temp == 30

    def test_supported_features_ac(self, ac_entity):
        sf = ac_entity._attr_supported_features
        assert sf & ClimateEntityFeature.TARGET_TEMPERATURE
        assert sf & ClimateEntityFeature.FAN_MODE
        assert sf & ClimateEntityFeature.TURN_ON
        assert sf & ClimateEntityFeature.TURN_OFF

    def test_hvac_modes(self, ac_entity):
        modes = ac_entity._attr_hvac_modes
        assert HVACMode.OFF in modes
        assert HVACMode.COOL in modes
        assert HVACMode.HEAT in modes
        assert HVACMode.AUTO in modes
        assert HVACMode.DRY in modes
        assert HVACMode.FAN_ONLY in modes

    def test_fan_modes(self, ac_entity):
        assert ac_entity._attr_fan_modes == ["auto", "low", "medium", "high", "turbo"]

    def test_hvac_mode_on_cool(self, ac_entity):
        assert ac_entity.hvac_mode == HVACMode.COOL

    def test_hvac_mode_off(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_ac_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": False}]
        coordinator.data["device_hvac_ac_1"] = dev
        entity = SberGenericClimate(coordinator, "device_hvac_ac_1", CATEGORY_CLIMATE["hvac_ac"])
        assert entity.hvac_mode == HVACMode.OFF

    def test_target_temperature(self, ac_entity):
        assert ac_entity.target_temperature == 24.0

    def test_current_temperature(self, ac_entity):
        # AC spec now has current_temp_key="temperature" — читаем из reported_state
        assert ac_entity.current_temperature == 22.5

    def test_fan_mode(self, ac_entity):
        assert ac_entity.fan_mode == "auto"

    @pytest.mark.asyncio
    async def test_set_hvac_mode_off(self, ac_entity, coordinator):
        await ac_entity.async_set_hvac_mode(HVACMode.OFF)
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1", [{"key": "on_off", "bool_value": False}]
        )

    @pytest.mark.asyncio
    async def test_set_hvac_mode_heat(self, ac_entity, coordinator):
        await ac_entity.async_set_hvac_mode(HVACMode.HEAT)
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1",
            [
                {"key": "on_off", "bool_value": True},
                {"key": "hvac_work_mode", "enum_value": "heat"},
            ],
        )

    @pytest.mark.asyncio
    async def test_set_temperature(self, ac_entity, coordinator):
        await ac_entity.async_set_temperature(**{ATTR_TEMPERATURE: 22})
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1", [{"key": "hvac_temp_set", "integer_value": 22}]
        )

    @pytest.mark.asyncio
    async def test_set_temperature_none_noop(self, ac_entity, coordinator):
        await ac_entity.async_set_temperature()
        coordinator.home_api.set_device_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_fan_mode(self, ac_entity, coordinator):
        await ac_entity.async_set_fan_mode("high")
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1", [{"key": "hvac_air_flow_power", "enum_value": "high"}]
        )

    @pytest.mark.asyncio
    async def test_turn_on(self, ac_entity, coordinator):
        await ac_entity.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1", [{"key": "on_off", "bool_value": True}]
        )

    @pytest.mark.asyncio
    async def test_turn_off(self, ac_entity, coordinator):
        await ac_entity.async_turn_off()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1", [{"key": "on_off", "bool_value": False}]
        )


class TestSberClimateHeater:
    def test_hvac_modes_heater(self, heater_entity):
        """Heater без hvac_modes_key → автоматически добавляется HEAT."""
        assert HVACMode.OFF in heater_entity._attr_hvac_modes
        assert HVACMode.HEAT in heater_entity._attr_hvac_modes

    def test_hvac_mode_off_when_on_off_false(self, heater_entity):
        assert heater_entity.hvac_mode == HVACMode.OFF

    def test_hvac_mode_heat_when_on(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_heater_1"])
        dev["desired_state"] = [
            {"key": "on_off", "bool_value": True},
            {"key": "hvac_temp_set", "integer_value": 21},
        ]
        coordinator.data["device_hvac_heater_1"] = dev
        entity = SberGenericClimate(coordinator, "device_hvac_heater_1", CATEGORY_CLIMATE["hvac_heater"])
        assert entity.hvac_mode == HVACMode.HEAT

    def test_fan_mode_no_state(self, heater_entity):
        # Heater has fan_mode_key but no state set → None
        # our fixture has low set, so it's "low"
        assert heater_entity.fan_mode == "low"


class TestClimateMapping:
    def test_sber_to_ha_mapping(self):
        assert SBER_TO_HA_HVAC["cool"] == HVACMode.COOL
        assert SBER_TO_HA_HVAC["heat"] == HVACMode.HEAT
        assert SBER_TO_HA_HVAC["auto"] == HVACMode.AUTO
        assert SBER_TO_HA_HVAC["fan"] == HVACMode.FAN_ONLY
        assert SBER_TO_HA_HVAC["fan_only"] == HVACMode.FAN_ONLY

    def test_ha_to_sber_roundtrip(self):
        assert HA_TO_SBER_HVAC[HVACMode.COOL] == "cool"
        assert HA_TO_SBER_HVAC[HVACMode.HEAT] == "heat"


class TestTargetTempParsing:
    def test_float_value(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_ac_1"])
        dev["desired_state"] = [
            {"key": "on_off", "bool_value": True},
            {"key": "hvac_temp_set", "float_value": 23.5},
        ]
        coordinator.data["device_hvac_ac_1"] = dev
        entity = SberGenericClimate(coordinator, "device_hvac_ac_1", CATEGORY_CLIMATE["hvac_ac"])
        assert entity.target_temperature == 23.5

    def test_missing_temp(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_ac_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": True}]
        coordinator.data["device_hvac_ac_1"] = dev
        entity = SberGenericClimate(coordinator, "device_hvac_ac_1", CATEGORY_CLIMATE["hvac_ac"])
        assert entity.target_temperature is None


class TestHvacHeaterNew:
    """Проверка новых параметров hvac_heater (current_temp)."""

    @pytest.fixture
    def heater(self, coordinator):
        return SberGenericClimate(
            coordinator, "device_hvac_heater_1", CATEGORY_CLIMATE["hvac_heater"]
        )

    def test_current_temperature_from_reported(self, heater):
        """Heater current_temp_key теперь 'temperature' → читается из reported."""
        assert heater.current_temperature == 21.0

    def test_min_max_temp_heater(self, heater):
        assert heater._attr_min_temp == 7
        assert heater._attr_max_temp == 30

    def test_step_heater(self, heater):
        assert heater._attr_target_temperature_step == 1


class TestHvacRadiator:
    """hvac_radiator 25-40 step 5."""

    @pytest.fixture
    def radiator(self, coordinator):
        return SberGenericClimate(
            coordinator, "device_hvac_radiator_1", CATEGORY_CLIMATE["hvac_radiator"]
        )

    def test_min_max_temp(self, radiator):
        assert radiator._attr_min_temp == 25
        assert radiator._attr_max_temp == 40

    def test_step(self, radiator):
        assert radiator._attr_target_temperature_step == 5

    def test_current_temperature(self, radiator):
        assert radiator.current_temperature == 27.0

    def test_target_temperature(self, radiator):
        assert radiator.target_temperature == 30.0


class TestHvacBoiler:
    """hvac_boiler 25-80 step 5."""

    @pytest.fixture
    def boiler(self, coordinator):
        return SberGenericClimate(
            coordinator, "device_hvac_boiler_1", CATEGORY_CLIMATE["hvac_boiler"]
        )

    def test_min_max_temp(self, boiler):
        assert boiler._attr_min_temp == 25
        assert boiler._attr_max_temp == 80

    def test_step(self, boiler):
        assert boiler._attr_target_temperature_step == 5

    def test_current_temperature(self, boiler):
        assert boiler.current_temperature == 55.0

    def test_target_temperature(self, boiler):
        assert boiler.target_temperature == 60.0


class TestHvacUnderfloor:
    """hvac_underfloor_heating 25-50 step 5."""

    @pytest.fixture
    def underfloor(self, coordinator):
        return SberGenericClimate(
            coordinator,
            "device_hvac_underfloor_1",
            CATEGORY_CLIMATE["hvac_underfloor_heating"],
        )

    def test_min_max_temp(self, underfloor):
        assert underfloor._attr_min_temp == 25
        assert underfloor._attr_max_temp == 50

    def test_step(self, underfloor):
        assert underfloor._attr_target_temperature_step == 5

    def test_current_temperature(self, underfloor):
        assert underfloor.current_temperature == 30.0

    def test_target_temperature(self, underfloor):
        assert underfloor.target_temperature == 35.0


class TestCurrentTempFallback:
    """Если current_temp_key задан, но в reported_state нет — вернуть None."""

    def test_missing_current_temp_returns_none(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_radiator_1"])
        dev["reported_state"] = []
        coordinator.data["device_hvac_radiator_1"] = dev
        entity = SberGenericClimate(
            coordinator, "device_hvac_radiator_1", CATEGORY_CLIMATE["hvac_radiator"]
        )
        assert entity.current_temperature is None

    def test_current_temp_integer_value(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hvac_ac_1"])
        dev["reported_state"] = [
            {"key": "on_off", "bool_value": True},
            {"key": "temperature", "integer_value": 23},
        ]
        coordinator.data["device_hvac_ac_1"] = dev
        entity = SberGenericClimate(
            coordinator, "device_hvac_ac_1", CATEGORY_CLIMATE["hvac_ac"]
        )
        assert entity.current_temperature == 23.0


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_climate_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # hvac_ac + hvac_heater + hvac_radiator + hvac_boiler + hvac_underfloor = 5
        assert len(entities) == 5
        ids = {e._device_id for e in entities}
        assert ids == {
            "device_hvac_ac_1",
            "device_hvac_heater_1",
            "device_hvac_radiator_1",
            "device_hvac_boiler_1",
            "device_hvac_underfloor_1",
        }
