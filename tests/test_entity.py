"""Tests for the SberHome base entity."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sberhome.entity import SberBaseEntity

from .conftest import MOCK_DEVICE_LIGHT, MOCK_DEVICE_CLIMATE_SENSOR


def _make_coordinator(devices: dict) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = devices
    return coordinator


class TestSberBaseEntity:
    @pytest.fixture
    def entity(self):
        devices = {"device_light_1": MOCK_DEVICE_LIGHT}
        coordinator = _make_coordinator(devices)
        return SberBaseEntity(coordinator, "device_light_1")

    @pytest.fixture
    def entity_with_suffix(self):
        devices = {"device_climate_1": MOCK_DEVICE_CLIMATE_SENSOR}
        coordinator = _make_coordinator(devices)
        return SberBaseEntity(coordinator, "device_climate_1", "temperature")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_light_1"

    def test_unique_id_with_suffix(self, entity_with_suffix):
        assert entity_with_suffix._attr_unique_id == "device_climate_1_temperature"

    def test_name(self, entity):
        assert entity._attr_name is None

    def test_device_data(self, entity):
        assert entity._device_data["id"] == "device_light_1"

    def test_device_info(self, entity):
        info = entity.device_info
        assert ("sberhome", "SN_LIGHT_001") in info["identifiers"]
        assert info["manufacturer"] == "Sber"
        assert info["model"] == "SBDV-00115"
        assert info["sw_version"] == "1.0.0"

    def test_get_desired_state_found(self, entity):
        state = entity._get_desired_state("on_off")
        assert state is not None
        assert state["bool_value"] is True

    def test_get_desired_state_not_found(self, entity):
        assert entity._get_desired_state("nonexistent") is None

    def test_get_reported_state_found(self, entity):
        state = entity._get_reported_state("on_off")
        assert state is not None
        assert state["bool_value"] is True

    def test_get_reported_state_missing_key(self):
        device = {**MOCK_DEVICE_LIGHT}
        del device["reported_state"]
        coordinator = _make_coordinator({"d": device})
        ent = SberBaseEntity(coordinator, "d")
        assert ent._get_reported_state("on_off") is None

    def test_get_attribute_found(self, entity):
        attr = entity._get_attribute("light_brightness")
        assert attr is not None
        assert "int_values" in attr

    def test_get_attribute_not_found(self, entity):
        assert entity._get_attribute("nonexistent") is None

    def test_available_when_device_exists(self, entity):
        entity.coordinator.last_update_success = True
        assert entity.available is True

    def test_unavailable_when_device_removed(self):
        devices = {"device_light_1": MOCK_DEVICE_LIGHT}
        coordinator = _make_coordinator(devices)
        coordinator.last_update_success = True
        ent = SberBaseEntity(coordinator, "device_light_1")
        # Simulate device disappearing from API
        del coordinator.data["device_light_1"]
        assert ent.available is False
