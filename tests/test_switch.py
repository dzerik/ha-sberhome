"""Tests for SberHome switch platform — sbermap-driven (PR #4 + PR #9).

Базовые SberSbermapSwitch (primary on_off) + SberAtHomeSwitch.
Extra-переключатели (child_lock/switch_led/alarm_mute) — в test_switch_extra.py,
групповые — в test_switch_groups.py.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.sberhome.aiosber.dto import AttributeValueType
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.switch import (
    SberAtHomeSwitch,
    SberSbermapSwitch,
    async_setup_entry,
)

from .conftest import MOCK_DEVICE_SWITCH, build_coordinator_caches


def _coord_with_raw(raw_devices: dict[str, dict]) -> MagicMock:
    """Coordinator-mock: DTO + sbermap entities + StateCache из raw-словарей."""
    coord = MagicMock()
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    cache = StateCache()
    cache.update_from_devices(coord.devices)
    coord.state_cache = cache
    coord.async_send_device_state = AsyncMock()
    return coord


def _switch_by_id(coord, device_id: str, unique_id: str) -> SberSbermapSwitch:
    """Helper: построить SberSbermapSwitch для конкретного unique_id."""
    ent = next(e for e in coord.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapSwitch(coord, device_id, ent)


class TestSbermapSwitch:
    @pytest.fixture
    def coord(self) -> MagicMock:
        return _coord_with_raw({"device_switch_1": MOCK_DEVICE_SWITCH})

    @pytest.fixture
    def entity(self, coord) -> SberSbermapSwitch:
        return _switch_by_id(coord, "device_switch_1", "device_switch_1")

    def test_unique_id(self, entity):
        """Primary switch без суффикса — unique_id совпадает с id устройства."""
        assert entity.unique_id == "device_switch_1"

    def test_is_on_true(self, entity):
        """on_off=true в состоянии → is_on True."""
        assert entity.is_on is True

    def test_is_on_false(self):
        """on_off=false → is_on False."""
        raw = copy.deepcopy(MOCK_DEVICE_SWITCH)
        raw["desired_state"] = [{"key": "on_off", "bool_value": False}]
        raw["reported_state"][0] = {"key": "on_off", "bool_value": False}
        coord = _coord_with_raw({"device_switch_1": raw})
        entity = _switch_by_id(coord, "device_switch_1", "device_switch_1")
        assert entity.is_on is False

    def test_is_on_none_when_entity_disappears(self, coord, entity):
        """Entity пропала из coordinator.entities → is_on None."""
        coord.entities["device_switch_1"] = []
        assert entity.is_on is None

    @pytest.mark.asyncio
    async def test_turn_on_sends_on_off_true(self, coord, entity):
        """turn_on → команда on_off=true (BOOL) для этого устройства."""
        await entity.async_turn_on()
        coord.async_send_device_state.assert_awaited_once()
        device_id, attrs = coord.async_send_device_state.await_args.args
        assert device_id == "device_switch_1"
        assert len(attrs) == 1
        assert attrs[0].key == "on_off"
        assert attrs[0].type is AttributeValueType.BOOL
        assert attrs[0].bool_value is True

    @pytest.mark.asyncio
    async def test_turn_off_sends_on_off_false(self, coord, entity):
        """turn_off → команда on_off=false."""
        await entity.async_turn_off()
        _, attrs = coord.async_send_device_state.await_args.args
        assert attrs[0].key == "on_off"
        assert attrs[0].bool_value is False


class TestAtHomeSwitch:
    @pytest.fixture
    def coord(self) -> MagicMock:
        coord = MagicMock()
        coord.at_home = True
        coord.async_set_at_home = AsyncMock()
        return coord

    @pytest.fixture
    def entity(self, coord) -> SberAtHomeSwitch:
        return SberAtHomeSwitch(coord)

    def test_is_on_mirrors_coordinator_at_home(self, coord, entity):
        """is_on транслирует coordinator.at_home напрямую."""
        assert entity.is_on is True
        coord.at_home = False
        assert entity.is_on is False

    def test_unavailable_when_at_home_unknown(self, coord, entity):
        """at_home=None (poll ещё не прошёл) → available False."""
        coord.at_home = None
        assert entity.available is False

    def test_grouped_into_scenarios_service_device(self, entity):
        """Entity прикреплена к virtual device 'Sber Scenarios'."""
        assert (DOMAIN, "scenarios") in entity.device_info["identifiers"]
        assert entity.entity_category is EntityCategory.CONFIG

    @pytest.mark.asyncio
    async def test_turn_on_calls_set_at_home(self, coord, entity):
        """turn_on → coordinator.async_set_at_home(True)."""
        await entity.async_turn_on()
        coord.async_set_at_home.assert_awaited_once_with(True)

    @pytest.mark.asyncio
    async def test_turn_off_calls_set_at_home(self, coord, entity):
        """turn_off → coordinator.async_set_at_home(False)."""
        await entity.async_turn_off()
        coord.async_set_at_home.assert_awaited_once_with(False)


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_switch_and_at_home(self):
        """Setup: SberSbermapSwitch для розетки + SberAtHomeSwitch (групп нет)."""
        coord = _coord_with_raw({"device_switch_1": MOCK_DEVICE_SWITCH})
        entry = MagicMock()
        entry.runtime_data = coord
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        sbermap_switches = [e for e in captured if isinstance(e, SberSbermapSwitch)]
        at_home = [e for e in captured if isinstance(e, SberAtHomeSwitch)]
        assert len(sbermap_switches) == 1
        assert sbermap_switches[0].unique_id == "device_switch_1"
        assert len(at_home) == 1
