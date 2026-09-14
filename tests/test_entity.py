"""Tests for the SberBaseEntity (sbermap-driven) — PR #8."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.entity import SberBaseEntity

from .conftest import MOCK_DEVICE_CLIMATE_SENSOR, MOCK_DEVICE_LIGHT


def _make_coordinator(devices: dict) -> MagicMock:
    coordinator = MagicMock()
    coordinator.data = devices
    # Populate state_cache with typed DTOs.
    cache = StateCache()
    for did, raw in devices.items():
        dto = DeviceDto.from_dict(raw)
        if dto is not None:
            cache._devices[did] = dto
    coordinator.state_cache = cache
    # devices property returns state_cache content.
    coordinator.devices = cache.get_all_devices()
    coordinator.entities = {}
    return coordinator


class TestSberBaseEntity:
    @pytest.fixture
    def entity(self):
        coordinator = _make_coordinator({"device_light_1": MOCK_DEVICE_LIGHT})
        return SberBaseEntity(coordinator, "device_light_1")

    @pytest.fixture
    def entity_with_suffix(self):
        coordinator = _make_coordinator({"device_climate_1": MOCK_DEVICE_CLIMATE_SENSOR})
        return SberBaseEntity(coordinator, "device_climate_1", "temperature")

    def test_unique_id_primary(self, entity):
        assert entity._attr_unique_id == "device_light_1"

    def test_unique_id_with_suffix(self, entity_with_suffix):
        assert entity_with_suffix._attr_unique_id == "device_climate_1_temperature"

    def test_name_primary_is_none(self, entity):
        assert entity._attr_name is None

    def test_device_info(self, entity):
        info = entity.device_info
        assert ("sberhome", "SN_LIGHT_001") in info["identifiers"]
        assert info["manufacturer"] == "Sber"
        assert info["model"] == "SBDV-00115"

    def test_available_when_device_exists(self, entity):
        entity.coordinator.last_update_success = True
        assert entity.available is True

    def test_unavailable_when_device_removed(self):
        coordinator = _make_coordinator({"device_light_1": MOCK_DEVICE_LIGHT})
        coordinator.last_update_success = True
        ent = SberBaseEntity(coordinator, "device_light_1")
        # Remove from both raw and typed cache.
        del coordinator.data["device_light_1"]
        coordinator.state_cache._devices.pop("device_light_1", None)
        assert ent.available is False


class TestSendAttrsFeedsTheTimeline:
    """Отправка команды из сущности пишет в трекер длительность, контекст и ошибки."""

    @staticmethod
    def _entity():
        from unittest.mock import AsyncMock

        from homeassistant.core import Context

        from custom_components.sberhome.command_tracker import CommandTracker

        coordinator = _make_coordinator({"device_light_1": MOCK_DEVICE_LIGHT})
        coordinator.command_tracker = CommandTracker()
        coordinator.async_send_device_state = AsyncMock()
        entity = SberBaseEntity(coordinator, "device_light_1")
        entity._context = Context(id="ctx-42")
        return entity

    @staticmethod
    def _attrs():
        from custom_components.sberhome.aiosber.dto.values import (
            AttributeValueDto,
            AttributeValueType,
        )

        return [AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True)]

    @pytest.mark.asyncio
    async def test_successful_send(self):
        entity = self._entity()
        await entity._async_send_attrs(self._attrs())
        [record] = entity.coordinator.command_tracker.snapshot()
        assert record["status"] == "pending"
        assert record["context_id"] == "ctx-42"
        assert record["http_ms"] is not None and record["http_ms"] >= 0

    @pytest.mark.asyncio
    async def test_failed_send_is_recorded_then_raised(self):
        from custom_components.sberhome.exceptions import SberConnectionError

        entity = self._entity()
        entity.coordinator.async_send_device_state.side_effect = SberConnectionError(
            "gateway timeout"
        )
        with pytest.raises(SberConnectionError):
            await entity._async_send_attrs(self._attrs())
        [record] = entity.coordinator.command_tracker.snapshot()
        assert record["status"] == "send_failed"
        assert "gateway timeout" in record["error"]
