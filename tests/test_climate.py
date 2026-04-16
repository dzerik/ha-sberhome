"""Tests for SberHome climate platform — sbermap-driven (PR #5 рефакторинга)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)

from custom_components.sberhome.climate import SberClimateEntity, async_setup_entry
from custom_components.sberhome.sbermap import (
    map_hvac_mode,
    map_hvac_mode_to_sber,
)
from custom_components.sberhome.sbermap.transform.climate_helpers import (
    climate_config_for,
)
from tests.conftest import build_coordinator_caches


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.devices, coord.entities = build_coordinator_caches(mock_devices_extra)
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    fake_client = AsyncMock()
    fake_client.devices = AsyncMock()
    coord.home_api.get_sber_client = AsyncMock(return_value=fake_client)
    coord._fake_client = fake_client
    coord.async_set_updated_data = MagicMock()
    coord._rebuild_dto_caches = MagicMock()
    return coord


def _ac(coordinator) -> SberClimateEntity:
    return SberClimateEntity(
        coordinator, "device_hvac_ac_1", climate_config_for("hvac_ac")
    )


def _heater(coordinator) -> SberClimateEntity:
    return SberClimateEntity(
        coordinator, "device_hvac_heater_1", climate_config_for("hvac_heater")
    )


class TestACState:
    @pytest.fixture
    def ac(self, coordinator):
        return _ac(coordinator)

    def test_unique_id(self, ac):
        assert ac._attr_unique_id == "device_hvac_ac_1"

    def test_min_max_temp(self, ac):
        assert ac._attr_min_temp == 16
        assert ac._attr_max_temp == 30

    def test_supported_features(self, ac):
        sf = ac._attr_supported_features
        assert sf & ClimateEntityFeature.TARGET_TEMPERATURE
        assert sf & ClimateEntityFeature.FAN_MODE
        assert sf & ClimateEntityFeature.TURN_ON
        assert sf & ClimateEntityFeature.TURN_OFF

    def test_hvac_modes(self, ac):
        modes = ac._attr_hvac_modes
        assert HVACMode.OFF in modes
        assert HVACMode.COOL in modes
        assert HVACMode.HEAT in modes
        assert HVACMode.AUTO in modes
        assert HVACMode.DRY in modes
        assert HVACMode.FAN_ONLY in modes

    def test_fan_modes(self, ac):
        assert ac._attr_fan_modes == ["auto", "low", "medium", "high", "turbo"]

    def test_hvac_mode_cool(self, ac):
        assert ac.hvac_mode is HVACMode.COOL

    def test_target_temperature(self, ac):
        assert ac.target_temperature == 24.0

    def test_current_temperature(self, ac):
        assert ac.current_temperature == 22.5

    def test_fan_mode(self, ac):
        assert ac.fan_mode == "auto"


class TestACCommands:
    @pytest.fixture
    def ac(self, coordinator):
        return _ac(coordinator)

    @pytest.mark.asyncio
    async def test_set_hvac_off(self, ac, coordinator):
        await ac.async_set_hvac_mode(HVACMode.OFF)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is False for a in attrs)

    @pytest.mark.asyncio
    async def test_set_hvac_heat(self, ac, coordinator):
        await ac.async_set_hvac_mode(HVACMode.HEAT)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is True for a in attrs)
        assert any(a.key == "hvac_work_mode" and a.enum_value == "heat" for a in attrs)

    @pytest.mark.asyncio
    async def test_set_temperature(self, ac, coordinator):
        await ac.async_set_temperature(**{ATTR_TEMPERATURE: 22})
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "hvac_temp_set" and a.integer_value == 22 for a in attrs)

    @pytest.mark.asyncio
    async def test_set_temperature_none_noop(self, ac, coordinator):
        await ac.async_set_temperature()
        coordinator._fake_client.devices.set_state.assert_not_called()

    @pytest.mark.asyncio
    async def test_set_fan_mode(self, ac, coordinator):
        await ac.async_set_fan_mode("high")
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "hvac_air_flow_power" and a.enum_value == "high" for a in attrs)


class TestHeater:
    @pytest.fixture
    def heater(self, coordinator):
        return _heater(coordinator)

    def test_hvac_modes_includes_heat(self, heater):
        # heater без hvac_modes spec → fallback HEAT.
        assert HVACMode.HEAT in heater._attr_hvac_modes
        assert HVACMode.OFF in heater._attr_hvac_modes

    def test_off_when_on_off_false(self, heater):
        assert heater.hvac_mode is HVACMode.OFF

    def test_min_max_temp(self, heater):
        assert heater._attr_min_temp == 7
        assert heater._attr_max_temp == 30


class TestModeMapping:
    def test_sber_to_ha_basic(self):
        assert map_hvac_mode("cool", is_on=True) is HVACMode.COOL
        assert map_hvac_mode("fan", is_on=True) is HVACMode.FAN_ONLY
        assert map_hvac_mode("fan_only", is_on=True) is HVACMode.FAN_ONLY

    def test_off_when_not_on(self):
        assert map_hvac_mode("cool", is_on=False) is HVACMode.OFF

    def test_reverse_off_returns_none(self):
        assert map_hvac_mode_to_sber(HVACMode.OFF) is None


class TestRadiator:
    @pytest.fixture
    def rad(self, coordinator):
        return SberClimateEntity(
            coordinator, "device_hvac_radiator_1", climate_config_for("hvac_radiator")
        )

    def test_min_max_temp(self, rad):
        assert rad._attr_min_temp == 25
        assert rad._attr_max_temp == 40

    def test_step(self, rad):
        assert rad._attr_target_temperature_step == 5

    def test_current_temperature(self, rad):
        assert rad.current_temperature == 27.0

    def test_target_temperature(self, rad):
        assert rad.target_temperature == 30.0


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_5_climate_entities(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._device_id for e in captured}
        assert ids == {
            "device_hvac_ac_1",
            "device_hvac_heater_1",
            "device_hvac_radiator_1",
            "device_hvac_boiler_1",
            "device_hvac_underfloor_1",
        }
