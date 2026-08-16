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


# ---------------------------------------------------------------------------
# SberScenarioEvent — «сценарий сработал» как HA-триггер
# ---------------------------------------------------------------------------

from types import SimpleNamespace  # noqa: E402

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto  # noqa: E402
from custom_components.sberhome.event import SberScenarioEvent  # noqa: E402


def _scenario_event(scenario_id="sc-1", name="X", scenarios=None) -> SberScenarioEvent:
    coord = MagicMock()
    coord.scenarios = (
        scenarios if scenarios is not None else [ScenarioDto(id=scenario_id, name=name)]
    )
    ev = SberScenarioEvent(coord, scenario_id, name)
    ev._trigger_event = MagicMock()
    ev.async_write_ha_state = MagicMock()
    return ev


class TestScenarioEvent:
    def test_fires_on_matching_scenario(self):
        ev = _scenario_event("sc-1")
        ev._handle_intent_event(
            SimpleNamespace(
                data={
                    "slug": None,
                    "scenario_id": "sc-1",
                    "name": "X",
                    "type": "SUCCESS",
                    "trigger_type": "phrase",
                }
            )
        )
        ev._trigger_event.assert_called_once()
        etype, attrs = ev._trigger_event.call_args[0]
        assert etype == "triggered"
        assert attrs["type"] == "SUCCESS"
        assert attrs["trigger_type"] == "phrase"
        ev.async_write_ha_state.assert_called_once()

    def test_ignores_other_scenario(self):
        ev = _scenario_event("sc-1")
        ev._handle_intent_event(SimpleNamespace(data={"slug": None, "scenario_id": "sc-2"}))
        ev._trigger_event.assert_not_called()

    def test_ignores_listener_event_to_avoid_double_fire(self):
        ev = _scenario_event("sc-1")
        ev._handle_intent_event(
            SimpleNamespace(data={"slug": "my_listener", "scenario_id": "sc-1"})
        )
        ev._trigger_event.assert_not_called()

    def test_available_reflects_scenario_presence(self):
        assert (
            _scenario_event("sc-1", scenarios=[ScenarioDto(id="sc-1", name="X")]).available is True
        )
        assert _scenario_event("sc-9", scenarios=[]).available is False


async def test_setup_creates_one_scenario_event_and_skips_malformed():
    """async_setup_entry создаёт SberScenarioEvent на валидный сценарий и
    пропускает без id/имени (EV-1 wiring guard)."""
    from custom_components.sberhome.event import async_setup_entry

    coord = MagicMock()
    coord.devices, coord.entities = {}, {}
    coord.scenarios = [
        ScenarioDto(id="sc-1", name="X"),
        ScenarioDto(id=None, name="Y"),
        ScenarioDto(id="sc-2", name=""),
    ]
    entry = MagicMock()
    entry.runtime_data = coord
    captured: list = []
    await async_setup_entry(MagicMock(), entry, captured.extend)
    events = [e for e in captured if isinstance(e, SberScenarioEvent)]
    assert len(events) == 1
    assert events[0].unique_id == "sberhome_scenario_event_sc-1"
