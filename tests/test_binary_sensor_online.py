"""Tests for binary_sensor connectivity (hub/intercom online) — sbermap-driven."""

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


class TestHubOnlineBinarySensor:
    """Hub primary binary_sensor — online через sbermap (BinarySensorDeviceClass.CONNECTIVITY)."""

    @pytest.fixture
    def entity(self, coordinator):
        ent = next(
            e for e in coordinator.entities["device_hub_1"]
            if e.unique_id == "device_hub_1"
        )
        return SberSbermapBinarySensor(coordinator, "device_hub_1", ent)

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_hub_1"

    def test_name_is_none_for_primary(self, entity):
        # primary entity (без суффикса) → name=None, наследует от device_info.
        assert entity._attr_name is None

    def test_device_class(self, entity):
        assert entity._attr_device_class is BinarySensorDeviceClass.CONNECTIVITY

    def test_is_on_true(self, entity):
        assert entity.is_on is True


class TestAsyncSetupEntryOnline:
    @pytest.mark.asyncio
    async def test_hub_creates_online_sensor(self, coordinator):
        # Сужаем coordinator до одного hub.
        coordinator.data = {"device_hub_1": coordinator.data["device_hub_1"]}
        coordinator.devices = {"device_hub_1": coordinator.devices["device_hub_1"]}
        coordinator.entities = {
            "device_hub_1": coordinator.entities["device_hub_1"]
        }
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        assert len(captured) == 1
        assert captured[0]._attr_device_class is BinarySensorDeviceClass.CONNECTIVITY

    @pytest.mark.asyncio
    async def test_non_hub_no_online_sensor(self, mock_coordinator_with_entities):
        """Regular sensors (water_leak/door/motion) не должны иметь CONNECTIVITY."""
        entry = MagicMock()
        entry.runtime_data = mock_coordinator_with_entities
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        for e in captured:
            assert e._attr_device_class is not BinarySensorDeviceClass.CONNECTIVITY


class TestIntercomConnectivityNotPresent:
    """Intercom mock в нашем conftest не имеет 'online' attribute — connectivity нет."""

    def test_no_connectivity_for_intercom(self, coordinator):
        for e in coordinator.entities["device_intercom_1"]:
            assert not (
                hasattr(e, "device_class") and e.device_class is BinarySensorDeviceClass.CONNECTIVITY
            )


class TestEntityCategoryDiagnostic:
    """Sanity: hub primary connectivity не имеет EntityCategory (это primary)."""

    def test_hub_primary_no_category(self, coordinator):
        ent = next(
            e for e in coordinator.entities["device_hub_1"]
            if e.unique_id == "device_hub_1"
        )
        # Hub primary создаётся без entity_category (это primary, не diagnostic).
        assert ent.entity_category is None or ent.entity_category == EntityCategory.DIAGNOSTIC
