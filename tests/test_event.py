"""Tests for the SberHome event platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sberhome.event import (
    SberGenericEvent,
    _has_feature,
    async_setup_entry,
)
from custom_components.sberhome.registry import CATEGORY_EVENTS

# Path to super()._handle_coordinator_update — defined in CoordinatorEntity.
_SUPER_UPDATE = "homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def button1_event(coordinator):
    spec = next(
        s for s in CATEGORY_EVENTS["scenario_button"] if s.key == "button_1_event"
    )
    return SberGenericEvent(coordinator, "device_scenario_1", spec)


class TestSberEventEntity:
    def test_unique_id(self, button1_event):
        assert button1_event._attr_unique_id == "device_scenario_1_button_1"

    def test_name(self, button1_event):
        assert button1_event._attr_name == "Button 1"

    def test_event_types(self, button1_event):
        assert button1_event._attr_event_types == ["click", "double_click"]

    def test_initial_last_seen(self, button1_event):
        assert button1_event._last_seen is None

    def test_handle_coordinator_update_triggers(self, button1_event):
        """_handle_coordinator_update should fire _trigger_event on first call."""
        with patch.object(button1_event, "_trigger_event") as mock_trigger, \
             patch("homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"):
            button1_event._handle_coordinator_update()
            mock_trigger.assert_called_once_with("click")

    def test_handle_coordinator_update_same_marker_no_trigger(self, button1_event):
        """Тот же marker (enum+timestamp) — не вызывать trigger дважды."""
        with patch.object(button1_event, "_trigger_event") as mock_trigger, \
             patch("homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"):
            button1_event._handle_coordinator_update()
            button1_event._handle_coordinator_update()
            mock_trigger.assert_called_once()

    def test_handle_coordinator_update_new_timestamp_fires_again(
        self, button1_event, coordinator, mock_devices_extra
    ):
        """Новый timestamp → новый marker → новый trigger."""
        with patch.object(button1_event, "_trigger_event") as mock_trigger, \
             patch("homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"):
            button1_event._handle_coordinator_update()
            # Update device with new timestamp
            dev = dict(mock_devices_extra["device_scenario_1"])
            dev["reported_state"] = [
                {"key": "button_1_event", "enum_value": "click", "timestamp": "2024-01-02T00:00:00Z"},
            ]
            coordinator.data["device_scenario_1"] = dev
            button1_event._handle_coordinator_update()
            assert mock_trigger.call_count == 2

    def test_handle_coordinator_update_unknown_event_type(self, coordinator, mock_devices_extra):
        """enum_value не в event_types — marker обновляется, но trigger не вызывается."""
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = [
            {"key": "button_1_event", "enum_value": "triple_click", "timestamp": "2024-01-01T00:00:00Z"},
        ]
        coordinator.data["device_scenario_1"] = dev
        spec = next(
            s for s in CATEGORY_EVENTS["scenario_button"] if s.key == "button_1_event"
        )
        entity = SberGenericEvent(coordinator, "device_scenario_1", spec)
        with patch.object(entity, "_trigger_event") as mock_trigger, \
             patch("homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"):
            entity._handle_coordinator_update()
            mock_trigger.assert_not_called()

    def test_handle_coordinator_update_no_state(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = []
        coordinator.data["device_scenario_1"] = dev
        spec = next(
            s for s in CATEGORY_EVENTS["scenario_button"] if s.key == "button_1_event"
        )
        entity = SberGenericEvent(coordinator, "device_scenario_1", spec)
        with patch.object(entity, "_trigger_event") as mock_trigger, \
             patch("homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"):
            entity._handle_coordinator_update()
            mock_trigger.assert_not_called()

    def test_handle_no_timestamp_marker_is_value(self, coordinator, mock_devices_extra):
        """Без timestamp marker = value, повторные вызовы не триггерят пока value не сменится."""
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = [
            {"key": "button_1_event", "enum_value": "click"},
        ]
        coordinator.data["device_scenario_1"] = dev
        spec = next(
            s for s in CATEGORY_EVENTS["scenario_button"] if s.key == "button_1_event"
        )
        entity = SberGenericEvent(coordinator, "device_scenario_1", spec)
        with patch.object(entity, "_trigger_event") as mock_trigger, \
             patch("homeassistant.helpers.update_coordinator.CoordinatorEntity._handle_coordinator_update"):
            entity._handle_coordinator_update()
            entity._handle_coordinator_update()
            mock_trigger.assert_called_once()


class TestHasFeatureHelper:
    """_has_feature смотрит в attributes ИЛИ reported_state."""

    def test_feature_in_reported_state(self):
        dev = {
            "attributes": [],
            "reported_state": [{"key": "button_1_event", "enum_value": "click"}],
        }
        assert _has_feature(dev, "button_1_event") is True

    def test_feature_in_attributes(self):
        dev = {
            "attributes": [{"key": "button_left_event", "enum_values": {}}],
            "reported_state": [],
        }
        assert _has_feature(dev, "button_left_event") is True

    def test_feature_missing(self):
        dev = {"attributes": [], "reported_state": []}
        assert _has_feature(dev, "button_1_event") is False

    def test_feature_no_sections(self):
        assert _has_feature({}, "button_1_event") is False


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_event_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # Two buttons per scenario device
        assert len(entities) == 2
        suffixes = {e._spec.suffix for e in entities}
        assert suffixes == {"button_1", "button_2"}

    @pytest.mark.asyncio
    async def test_only_present_buttons_create_entity(self, mock_devices_extra):
        """Устройство с одним button_1_event → создаётся ТОЛЬКО одна event entity."""
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = [
            {"key": "button_1_event", "enum_value": "click"},
        ]
        mock_devices_extra["device_scenario_1"] = dev

        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        # Только одна кнопка в reported_state → одна entity
        scenario = [e for e in entities if e._device_id == "device_scenario_1"]
        assert len(scenario) == 1
        assert scenario[0]._spec.key == "button_1_event"

    @pytest.mark.asyncio
    async def test_directional_buttons(self, mock_devices_extra):
        """Устройство с button_left_event → directional event entity."""
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = [
            {"key": "button_left_event", "enum_value": "click"},
            {"key": "button_right_event", "enum_value": "click"},
        ]
        mock_devices_extra["device_scenario_1"] = dev

        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        scenario = [e for e in entities if e._device_id == "device_scenario_1"]
        assert len(scenario) == 2
        keys = {e._spec.key for e in scenario}
        assert keys == {"button_left_event", "button_right_event"}

    @pytest.mark.asyncio
    async def test_generic_button_event(self, mock_devices_extra):
        """button_event (обобщённое) для одноклавишных."""
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = [
            {"key": "button_event", "enum_value": "click"},
        ]
        mock_devices_extra["device_scenario_1"] = dev

        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        scenario = [e for e in entities if e._device_id == "device_scenario_1"]
        assert len(scenario) == 1
        assert scenario[0]._spec.suffix == "button"

    @pytest.mark.asyncio
    async def test_feature_via_attributes_only(self, mock_devices_extra):
        """Если button_3_event присутствует только в attributes — entity всё равно создаётся."""
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = []
        dev["attributes"] = [
            {"key": "button_3_event", "enum_values": {"values": ["click"]}},
        ]
        mock_devices_extra["device_scenario_1"] = dev

        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        scenario = [e for e in entities if e._device_id == "device_scenario_1"]
        assert len(scenario) == 1
        assert scenario[0]._spec.key == "button_3_event"

    @pytest.mark.asyncio
    async def test_no_buttons_no_entities(self, mock_devices_extra):
        """Сценарник вообще без button_*_event → 0 entity."""
        dev = dict(mock_devices_extra["device_scenario_1"])
        dev["reported_state"] = []
        dev["attributes"] = []
        mock_devices_extra["device_scenario_1"] = dev

        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        scenario = [e for e in entities if e._device_id == "device_scenario_1"]
        assert scenario == []
