"""Tests for SberHome extra switches — sbermap-driven (PR #4).

child_lock / night_mode / ionization / aromatization / decontaminate / alarm_mute
обслуживаются единым `SberSbermapSwitch` через `state_attribute_key` поле.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.sberhome.switch import SberSbermapSwitch, async_setup_entry
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


def _switch(coordinator, device_id: str, unique_id: str) -> SberSbermapSwitch:
    ent = next(e for e in coordinator.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapSwitch(coordinator, device_id, ent)


class TestKettleChildLock:
    @pytest.fixture
    def entity(self, coordinator):
        return _switch(coordinator, "device_kettle_1", "device_kettle_1_child_lock")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_kettle_1_child_lock"

    def test_entity_category(self, entity):
        assert entity._attr_entity_category is EntityCategory.CONFIG

    def test_icon(self, entity):
        assert entity._attr_icon == "mdi:lock"

    def test_is_on_false(self, entity):
        assert entity.is_on is False

    @pytest.mark.asyncio
    async def test_turn_on_sends_correct_key(self, entity, coordinator):
        await entity.async_turn_on()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "child_lock" and a.bool_value is True for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_off_sends_correct_key(self, entity, coordinator):
        await entity.async_turn_off()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "child_lock" and a.bool_value is False for a in attrs)


class TestACNightMode:
    @pytest.fixture
    def entity(self, coordinator):
        return _switch(coordinator, "device_hvac_ac_1", "device_hvac_ac_1_night_mode")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_hvac_ac_1_night_mode"

    def test_icon(self, entity):
        assert entity._attr_icon == "mdi:weather-night"


class TestAirPurifierExtras:
    def test_aromatization(self, coordinator):
        e = _switch(
            coordinator,
            "device_hvac_purifier_1",
            "device_hvac_purifier_1_aromatization",
        )
        assert e._attr_icon == "mdi:scent"

    def test_decontaminate(self, coordinator):
        e = _switch(
            coordinator,
            "device_hvac_purifier_1",
            "device_hvac_purifier_1_decontaminate",
        )
        assert e._attr_icon == "mdi:shield-sun"

    def test_ionization_is_on(self, coordinator):
        e = _switch(
            coordinator,
            "device_hvac_purifier_1",
            "device_hvac_purifier_1_ionization",
        )
        # mock fixture has hvac_ionization=True
        assert e.is_on is True


class TestGasSmokeAlarmMute:
    def test_gas_alarm_mute(self, coordinator):
        e = _switch(coordinator, "device_gas_1", "device_gas_1_alarm_mute")
        assert e._attr_icon == "mdi:bell-off"

    def test_smoke_alarm_mute(self, coordinator):
        e = _switch(coordinator, "device_smoke_1", "device_smoke_1_alarm_mute")
        assert e._attr_icon == "mdi:bell-off"


class TestAsyncSetupEntryExtra:
    @pytest.mark.asyncio
    async def test_creates_all_extra_switches(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._attr_unique_id for e in captured}

        # primary on_off
        assert "device_kettle_1" in ids
        # extras
        assert "device_kettle_1_child_lock" in ids
        assert "device_hvac_ac_1_night_mode" in ids
        assert "device_hvac_ac_1_ionization" in ids
        assert "device_humidifier_1_night_mode" in ids
        assert "device_humidifier_1_ionization" in ids
        assert "device_hvac_purifier_1_night_mode" in ids
        assert "device_hvac_purifier_1_ionization" in ids
        assert "device_hvac_purifier_1_aromatization" in ids
        assert "device_hvac_purifier_1_decontaminate" in ids
        assert "device_gas_1_alarm_mute" in ids
        assert "device_smoke_1_alarm_mute" in ids
        assert "device_vacuum_1_child_lock" in ids
