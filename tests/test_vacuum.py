"""Tests for the SberHome vacuum platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.vacuum import VacuumActivity, VacuumEntityFeature

from custom_components.sberhome.vacuum import (
    SBER_TO_HA_STATE,
    SberVacuumEntity,
    async_setup_entry,
)
from custom_components.sberhome.registry import CATEGORY_VACUUMS


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def vacuum_entity(coordinator):
    return SberVacuumEntity(coordinator, "device_vacuum_1", CATEGORY_VACUUMS["vacuum_cleaner"])


class TestSberVacuum:
    def test_unique_id(self, vacuum_entity):
        assert vacuum_entity._attr_unique_id == "device_vacuum_1"

    def test_name(self, vacuum_entity):
        assert vacuum_entity._attr_name is None

    def test_supported_features(self, vacuum_entity):
        sf = vacuum_entity._attr_supported_features
        assert sf & VacuumEntityFeature.START
        assert sf & VacuumEntityFeature.PAUSE
        assert sf & VacuumEntityFeature.STOP
        assert sf & VacuumEntityFeature.RETURN_HOME
        assert sf & VacuumEntityFeature.LOCATE
        assert sf & VacuumEntityFeature.BATTERY
        assert sf & VacuumEntityFeature.STATE

    def test_activity_cleaning(self, vacuum_entity):
        assert vacuum_entity.activity == VacuumActivity.CLEANING

    @pytest.mark.parametrize(
        "status,expected",
        [
            ("cleaning", VacuumActivity.CLEANING),
            ("running", VacuumActivity.CLEANING),
            ("paused", VacuumActivity.PAUSED),
            ("returning", VacuumActivity.RETURNING),
            ("docked", VacuumActivity.DOCKED),
            ("charging", VacuumActivity.DOCKED),
            ("idle", VacuumActivity.IDLE),
            ("error", VacuumActivity.ERROR),
        ],
    )
    def test_activity_mapping(self, coordinator, mock_devices_extra, status, expected):
        dev = dict(mock_devices_extra["device_vacuum_1"])
        dev["reported_state"] = [
            {"key": "vacuum_cleaner_status", "enum_value": status},
            {"key": "battery_percentage", "integer_value": 50},
        ]
        coordinator.data["device_vacuum_1"] = dev
        entity = SberVacuumEntity(coordinator, "device_vacuum_1", CATEGORY_VACUUMS["vacuum_cleaner"])
        assert entity.activity == expected

    def test_activity_unknown_falls_back_to_idle(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_vacuum_1"])
        dev["reported_state"] = [{"key": "vacuum_cleaner_status", "enum_value": "exploring"}]
        coordinator.data["device_vacuum_1"] = dev
        entity = SberVacuumEntity(coordinator, "device_vacuum_1", CATEGORY_VACUUMS["vacuum_cleaner"])
        assert entity.activity == VacuumActivity.IDLE

    def test_activity_none_without_state(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_vacuum_1"])
        dev["reported_state"] = []
        coordinator.data["device_vacuum_1"] = dev
        entity = SberVacuumEntity(coordinator, "device_vacuum_1", CATEGORY_VACUUMS["vacuum_cleaner"])
        assert entity.activity is None

    def test_battery_level(self, vacuum_entity):
        assert vacuum_entity.battery_level == 67

    def test_battery_level_none(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_vacuum_1"])
        dev["reported_state"] = []
        coordinator.data["device_vacuum_1"] = dev
        entity = SberVacuumEntity(coordinator, "device_vacuum_1", CATEGORY_VACUUMS["vacuum_cleaner"])
        assert entity.battery_level is None

    @pytest.mark.asyncio
    async def test_start(self, vacuum_entity, coordinator):
        await vacuum_entity.async_start()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_vacuum_1",
            [{"key": "vacuum_cleaner_command", "enum_value": "start"}],
        )
        coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause(self, vacuum_entity, coordinator):
        await vacuum_entity.async_pause()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_vacuum_1",
            [{"key": "vacuum_cleaner_command", "enum_value": "pause"}],
        )

    @pytest.mark.asyncio
    async def test_stop(self, vacuum_entity, coordinator):
        await vacuum_entity.async_stop()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_vacuum_1",
            [{"key": "vacuum_cleaner_command", "enum_value": "stop"}],
        )

    @pytest.mark.asyncio
    async def test_return_to_base(self, vacuum_entity, coordinator):
        await vacuum_entity.async_return_to_base()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_vacuum_1",
            [{"key": "vacuum_cleaner_command", "enum_value": "return_to_base"}],
        )

    @pytest.mark.asyncio
    async def test_locate(self, vacuum_entity, coordinator):
        await vacuum_entity.async_locate()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_vacuum_1",
            [{"key": "vacuum_cleaner_command", "enum_value": "locate"}],
        )


class TestSberToHaStateMapping:
    def test_all_statuses_mapped(self):
        assert "cleaning" in SBER_TO_HA_STATE
        assert "charging" in SBER_TO_HA_STATE
        assert "error" in SBER_TO_HA_STATE


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_vacuum_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        assert len(entities) == 1
        assert entities[0]._device_id == "device_vacuum_1"
