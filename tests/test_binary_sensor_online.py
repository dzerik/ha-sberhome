"""Tests for SberHome binary sensor online (connectivity) for hub/intercom devices."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from custom_components.sberhome.binary_sensor import (
    SberGenericBinarySensor,
    _has_reported,
    async_setup_entry,
)
from custom_components.sberhome.registry import BinarySensorSpec


ONLINE_SPEC = BinarySensorSpec(
    "online",
    "connectivity",
    BinarySensorDeviceClass.CONNECTIVITY,
    EntityCategory.DIAGNOSTIC,
)


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    return coord


class TestHubOnlineBinarySensor:
    @pytest.fixture
    def entity(self, coordinator):
        return SberGenericBinarySensor(coordinator, "device_hub_1", ONLINE_SPEC)

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_hub_1_connectivity"

    def test_name(self, entity):
        assert entity._attr_name == "Connectivity"  # secondary → suffix

    def test_device_class(self, entity):
        assert entity.device_class == BinarySensorDeviceClass.CONNECTIVITY

    def test_entity_category(self, entity):
        assert entity._attr_entity_category == EntityCategory.DIAGNOSTIC

    def test_is_on_true(self, entity):
        assert entity.is_on is True

    def test_is_on_false(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_hub_1"])
        dev["reported_state"] = [{"key": "online", "bool_value": False}]
        coordinator.data["device_hub_1"] = dev
        entity = SberGenericBinarySensor(coordinator, "device_hub_1", ONLINE_SPEC)
        assert entity.is_on is False


class TestHasReportedHelper:
    def test_has_reported_true(self, mock_devices_extra):
        assert _has_reported(mock_devices_extra["device_hub_1"], "online") is True

    def test_has_reported_false(self, mock_devices_extra):
        assert _has_reported(mock_devices_extra["device_hub_1"], "nonexistent") is False

    def test_no_reported_state_key(self):
        assert _has_reported({}, "anything") is False


class TestAsyncSetupEntryOnline:
    @pytest.mark.asyncio
    async def test_hub_creates_online_sensor(self, mock_devices_extra):
        # Only keep the hub
        coordinator = MagicMock()
        coordinator.data = {"device_hub_1": mock_devices_extra["device_hub_1"]}
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # Only online connectivity sensor
        assert len(entities) == 1
        assert entities[0]._attr_unique_id == "device_hub_1_connectivity"
        assert entities[0].device_class == BinarySensorDeviceClass.CONNECTIVITY

    @pytest.mark.asyncio
    async def test_non_hub_no_online_sensor(self, mock_devices):
        """Regular devices (not hub/intercom) don't get connectivity sensor."""
        coordinator = MagicMock()
        coordinator.data = mock_devices
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        for e in entities:
            assert e.device_class != BinarySensorDeviceClass.CONNECTIVITY
