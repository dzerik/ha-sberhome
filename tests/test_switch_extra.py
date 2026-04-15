"""Tests for SberHome extra switches (child_lock, night_mode) and declarative setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.sberhome.switch import (
    SberExtraSwitch,
    SberGenericSwitch,
    _has_attribute,
    async_setup_entry,
)
from custom_components.sberhome.registry import (
    CATEGORY_EXTRA_SWITCHES,
    CATEGORY_SWITCHES,
    ExtraSwitchSpec,
)


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


class TestSberExtraSwitchChildLock:
    @pytest.fixture
    def child_lock_kettle(self, coordinator):
        spec = CATEGORY_EXTRA_SWITCHES["kettle"][0]
        return SberExtraSwitch(coordinator, "device_kettle_1", spec)

    def test_unique_id(self, child_lock_kettle):
        assert child_lock_kettle._attr_unique_id == "device_kettle_1_child_lock"

    def test_name(self, child_lock_kettle):
        assert child_lock_kettle._attr_name == "Child Lock"

    def test_entity_category(self, child_lock_kettle):
        assert child_lock_kettle._attr_entity_category == EntityCategory.CONFIG

    def test_icon(self, child_lock_kettle):
        assert child_lock_kettle._attr_icon == "mdi:lock"

    def test_is_on_false(self, child_lock_kettle):
        assert child_lock_kettle.is_on is False

    @pytest.mark.asyncio
    async def test_turn_on(self, child_lock_kettle, coordinator):
        await child_lock_kettle.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_kettle_1", [{"key": "child_lock", "bool_value": True}]
        )
        coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_turn_off(self, child_lock_kettle, coordinator):
        await child_lock_kettle.async_turn_off()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_kettle_1", [{"key": "child_lock", "bool_value": False}]
        )


class TestSberExtraSwitchNightMode:
    @pytest.fixture
    def night_mode_ac(self, coordinator):
        spec = CATEGORY_EXTRA_SWITCHES["hvac_ac"][0]
        return SberExtraSwitch(coordinator, "device_hvac_ac_1", spec)

    def test_unique_id(self, night_mode_ac):
        assert night_mode_ac._attr_unique_id == "device_hvac_ac_1_night_mode"

    def test_icon(self, night_mode_ac):
        assert night_mode_ac._attr_icon == "mdi:weather-night"

    def test_is_on_false(self, night_mode_ac):
        assert night_mode_ac.is_on is False


class TestHasAttributeHelper:
    def test_has_attribute_present(self, mock_devices_extra):
        assert _has_attribute(mock_devices_extra["device_kettle_1"], "child_lock") is True

    def test_has_attribute_missing(self, mock_devices_extra):
        assert _has_attribute(mock_devices_extra["device_kettle_1"], "nonexistent") is False

    def test_no_attributes_key(self):
        # switch._has_attribute returns False when no attributes key
        assert _has_attribute({}, "child_lock") is False


class TestGenericSwitchKettle:
    """Kettle has CATEGORY_SWITCHES entry and should produce on_off switch."""

    def test_kettle_on_off_switch(self, coordinator):
        spec = CATEGORY_SWITCHES["kettle"]
        entity = SberGenericSwitch(coordinator, "device_kettle_1", spec)
        assert entity._attr_unique_id == "device_kettle_1"
        assert entity.is_on is False


def _extra(category: str, key: str) -> ExtraSwitchSpec:
    for s in CATEGORY_EXTRA_SWITCHES[category]:
        if s.key == key:
            return s
    raise KeyError(f"{category}/{key}")


class TestAcIonization:
    """hvac_ac → hvac_ionization extra switch."""

    @pytest.fixture
    def ion(self, coordinator):
        return SberExtraSwitch(
            coordinator, "device_hvac_ac_1", _extra("hvac_ac", "hvac_ionization")
        )

    def test_unique_id(self, ion):
        assert ion._attr_unique_id == "device_hvac_ac_1_ionization"

    def test_icon(self, ion):
        assert ion._attr_icon == "mdi:flash"

    def test_is_on_false(self, ion):
        assert ion.is_on is False

    @pytest.mark.asyncio
    async def test_turn_on(self, ion, coordinator):
        await ion.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_ac_1", [{"key": "hvac_ionization", "bool_value": True}]
        )


class TestHumidifierIonization:
    @pytest.fixture
    def ion(self, coordinator):
        return SberExtraSwitch(
            coordinator,
            "device_humidifier_1",
            _extra("hvac_humidifier", "hvac_ionization"),
        )

    def test_unique_id(self, ion):
        assert ion._attr_unique_id == "device_humidifier_1_ionization"

    def test_is_on_false(self, ion):
        assert ion.is_on is False


class TestAirPurifierExtras:
    """hvac_air_purifier: night_mode + ionization + aromatization + decontaminate."""

    def test_night_mode(self, coordinator):
        spec = _extra("hvac_air_purifier", "hvac_night_mode")
        entity = SberExtraSwitch(coordinator, "device_hvac_purifier_1", spec)
        assert entity._attr_unique_id == "device_hvac_purifier_1_night_mode"
        assert entity._attr_icon == "mdi:weather-night"
        assert entity.is_on is False

    def test_ionization_on(self, coordinator):
        spec = _extra("hvac_air_purifier", "hvac_ionization")
        entity = SberExtraSwitch(coordinator, "device_hvac_purifier_1", spec)
        # fixture has hvac_ionization=True in desired
        assert entity.is_on is True

    def test_aromatization(self, coordinator):
        spec = _extra("hvac_air_purifier", "hvac_aromatization")
        entity = SberExtraSwitch(coordinator, "device_hvac_purifier_1", spec)
        assert entity._attr_unique_id == "device_hvac_purifier_1_aromatization"
        assert entity._attr_icon == "mdi:scent"
        assert entity.is_on is False

    def test_decontaminate(self, coordinator):
        spec = _extra("hvac_air_purifier", "hvac_decontaminate")
        entity = SberExtraSwitch(coordinator, "device_hvac_purifier_1", spec)
        assert entity._attr_unique_id == "device_hvac_purifier_1_decontaminate"
        assert entity._attr_icon == "mdi:shield-sun"
        assert entity.is_on is False

    @pytest.mark.asyncio
    async def test_aromatization_turn_on(self, coordinator):
        spec = _extra("hvac_air_purifier", "hvac_aromatization")
        entity = SberExtraSwitch(coordinator, "device_hvac_purifier_1", spec)
        await entity.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_hvac_purifier_1",
            [{"key": "hvac_aromatization", "bool_value": True}],
        )


class TestGasSmokeAlarmMute:
    """sensor_gas, sensor_smoke → alarm_mute extra switch."""

    def test_gas_alarm_mute(self, coordinator):
        spec = _extra("sensor_gas", "alarm_mute")
        entity = SberExtraSwitch(coordinator, "device_gas_1", spec)
        assert entity._attr_unique_id == "device_gas_1_alarm_mute"
        assert entity._attr_icon == "mdi:bell-off"
        assert entity.is_on is False

    def test_smoke_alarm_mute(self, coordinator):
        spec = _extra("sensor_smoke", "alarm_mute")
        entity = SberExtraSwitch(coordinator, "device_smoke_1", spec)
        assert entity._attr_unique_id == "device_smoke_1_alarm_mute"
        assert entity._attr_icon == "mdi:bell-off"

    @pytest.mark.asyncio
    async def test_gas_alarm_mute_turn_on(self, coordinator):
        spec = _extra("sensor_gas", "alarm_mute")
        entity = SberExtraSwitch(coordinator, "device_gas_1", spec)
        await entity.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_gas_1", [{"key": "alarm_mute", "bool_value": True}]
        )


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_extra_switches(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)

        ids_suffixes = [(e._device_id, e._spec.suffix) for e in entities]
        # Kettle: on_off switch + child_lock extra = 2
        assert ("device_kettle_1", "") in ids_suffixes
        assert ("device_kettle_1", "child_lock") in ids_suffixes
        # HVAC AC: night_mode + ionization
        assert ("device_hvac_ac_1", "night_mode") in ids_suffixes
        assert ("device_hvac_ac_1", "ionization") in ids_suffixes
        # Humidifier: night_mode + ionization
        assert ("device_humidifier_1", "night_mode") in ids_suffixes
        assert ("device_humidifier_1", "ionization") in ids_suffixes
        # Air purifier: night_mode + ionization + aromatization + decontaminate
        assert ("device_hvac_purifier_1", "night_mode") in ids_suffixes
        assert ("device_hvac_purifier_1", "ionization") in ids_suffixes
        assert ("device_hvac_purifier_1", "aromatization") in ids_suffixes
        assert ("device_hvac_purifier_1", "decontaminate") in ids_suffixes
        # Gas / Smoke: alarm_mute
        assert ("device_gas_1", "alarm_mute") in ids_suffixes
        assert ("device_smoke_1", "alarm_mute") in ids_suffixes
        # Vacuum: child_lock extra
        assert ("device_vacuum_1", "child_lock") in ids_suffixes

    @pytest.mark.asyncio
    async def test_no_extra_switch_when_attribute_missing(self):
        """Device без attribute-флага → extra switch не создаётся."""
        # Create a kettle without child_lock in attributes
        device = {
            "id": "dev_kettle_no_lock",
            "serial_number": "SN",
            "name": {"name": "Kettle"},
            "image_set_type": "kettle",
            "sw_version": "1",
            "device_info": {"manufacturer": "Sber", "model": "K"},
            "desired_state": [{"key": "on_off", "bool_value": False}],
            "reported_state": [],
            "attributes": [],  # no child_lock attribute
        }
        coordinator = MagicMock()
        coordinator.data = {"dev_kettle_no_lock": device}
        coordinator.home_api = AsyncMock()
        coordinator.home_api.get_cached_devices = MagicMock(return_value=coordinator.data)
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # Only the primary on_off switch, no child_lock extra
        assert len(entities) == 1
        assert entities[0]._spec.suffix == ""

    def test_extra_switch_spec_default_category(self):
        spec = ExtraSwitchSpec("some_key", "some_suffix")
        assert spec.entity_category == EntityCategory.CONFIG
