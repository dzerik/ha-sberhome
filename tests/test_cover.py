"""Tests for the SberHome cover platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.cover import CoverDeviceClass, CoverEntityFeature

from custom_components.sberhome.cover import SberGenericCover, async_setup_entry
from custom_components.sberhome.registry import CATEGORY_COVERS


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def curtain_entity(coordinator):
    return SberGenericCover(coordinator, "device_curtain_1", CATEGORY_COVERS["curtain"])


@pytest.fixture
def gate_entity(coordinator):
    return SberGenericCover(coordinator, "device_gate_1", CATEGORY_COVERS["gate"])


class TestSberGenericCurtain:
    def test_unique_id(self, curtain_entity):
        assert curtain_entity._attr_unique_id == "device_curtain_1"

    def test_name(self, curtain_entity):
        assert curtain_entity._attr_name is None

    def test_device_class(self, curtain_entity):
        assert curtain_entity._attr_device_class == CoverDeviceClass.CURTAIN

    def test_supported_features(self, curtain_entity):
        sf = curtain_entity._attr_supported_features
        assert sf & CoverEntityFeature.OPEN
        assert sf & CoverEntityFeature.CLOSE
        assert sf & CoverEntityFeature.STOP
        assert sf & CoverEntityFeature.SET_POSITION

    def test_current_cover_position(self, curtain_entity):
        assert curtain_entity.current_cover_position == 70

    def test_is_closed_opened(self, curtain_entity):
        assert curtain_entity.is_closed is False

    def test_is_opening_false(self, curtain_entity):
        assert curtain_entity.is_opening is False

    def test_is_closing_false(self, curtain_entity):
        assert curtain_entity.is_closing is False

    @pytest.mark.asyncio
    async def test_open_cover(self, curtain_entity, coordinator):
        await curtain_entity.async_open_cover()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_curtain_1", [{"key": "open_set", "integer_value": 100}]
        )
        coordinator.async_set_updated_data.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_cover(self, curtain_entity, coordinator):
        await curtain_entity.async_close_cover()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_curtain_1", [{"key": "open_set", "integer_value": 0}]
        )

    @pytest.mark.asyncio
    async def test_set_position(self, curtain_entity, coordinator):
        from homeassistant.components.cover import ATTR_POSITION

        await curtain_entity.async_set_cover_position(**{ATTR_POSITION: 42})
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_curtain_1", [{"key": "open_set", "integer_value": 42}]
        )

    @pytest.mark.asyncio
    async def test_stop_cover(self, curtain_entity, coordinator):
        await curtain_entity.async_stop_cover()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_curtain_1", [{"key": "open_state", "enum_value": "stop"}]
        )


class TestSberGenericCoverStates:
    def test_is_closed_gate_closed(self, gate_entity):
        assert gate_entity.is_closed is True

    def test_is_opening_true(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_curtain_1"])
        dev["reported_state"] = [{"key": "open_state", "enum_value": "opening"}]
        coordinator.data["device_curtain_1"] = dev
        entity = SberGenericCover(coordinator, "device_curtain_1", CATEGORY_COVERS["curtain"])
        assert entity.is_opening is True
        assert entity.is_closing is False

    def test_is_closing_true(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_curtain_1"])
        dev["reported_state"] = [{"key": "open_state", "enum_value": "closing"}]
        coordinator.data["device_curtain_1"] = dev
        entity = SberGenericCover(coordinator, "device_curtain_1", CATEGORY_COVERS["curtain"])
        assert entity.is_closing is True

    def test_is_closed_fallback_to_position_zero(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_curtain_1"])
        dev["reported_state"] = [{"key": "open_percentage", "integer_value": 0}]
        coordinator.data["device_curtain_1"] = dev
        entity = SberGenericCover(coordinator, "device_curtain_1", CATEGORY_COVERS["curtain"])
        assert entity.is_closed is True

    def test_is_closed_none_when_no_data(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_curtain_1"])
        dev["reported_state"] = []
        coordinator.data["device_curtain_1"] = dev
        entity = SberGenericCover(coordinator, "device_curtain_1", CATEGORY_COVERS["curtain"])
        assert entity.is_closed is None

    def test_current_position_missing(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_curtain_1"])
        dev["reported_state"] = []
        coordinator.data["device_curtain_1"] = dev
        entity = SberGenericCover(coordinator, "device_curtain_1", CATEGORY_COVERS["curtain"])
        assert entity.current_cover_position is None


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_entities_for_covers(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []

        def capture(ents):
            entities.extend(ents)

        await async_setup_entry(MagicMock(), entry, capture)

        # curtain + gate + window_blind = 3 cover entities
        assert len(entities) == 3
        ids = {e._device_id for e in entities}
        assert ids == {"device_curtain_1", "device_gate_1", "device_blind_1"}

    @pytest.mark.asyncio
    async def test_no_covers_for_unrelated_devices(self, mock_devices):
        coordinator = MagicMock()
        coordinator.data = mock_devices
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        assert entities == []
