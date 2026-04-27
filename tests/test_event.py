"""Tests for SberHome event platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sberhome.event import SberSbermapEvent, async_setup_entry
from tests.conftest import build_coordinator_caches


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.devices, coord.entities = build_coordinator_caches(mock_devices_extra)
    return coord


def _event(coordinator, device_id: str, unique_id: str) -> SberSbermapEvent:
    ent = next(e for e in coordinator.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapEvent(coordinator, device_id, ent)


class TestScenarioButton:
    @pytest.fixture
    def button1(self, coordinator):
        return _event(coordinator, "device_scenario_1", "device_scenario_1_button_1_event")

    def test_unique_id(self, button1):
        assert button1._attr_unique_id == "device_scenario_1_button_1_event"

    def test_event_types(self, button1):
        assert "click" in button1._attr_event_types
        assert "double_click" in button1._attr_event_types
        assert "long_press" in button1._attr_event_types


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_scenario_button_events(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._attr_unique_id for e in captured}
        assert "device_scenario_1_button_1_event" in ids
        assert "device_scenario_1_button_2_event" in ids
