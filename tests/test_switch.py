"""Tests for SberHome switch entity — sbermap-driven (PR #4)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.switch import SberSbermapSwitch, async_setup_entry


@pytest.fixture
def coordinator(mock_coordinator_with_entities):
    coord = mock_coordinator_with_entities
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=coord.data)
    fake_client = AsyncMock()
    fake_client.devices = AsyncMock()
    coord.home_api.get_sber_client = AsyncMock(return_value=fake_client)
    coord._fake_client = fake_client
    coord.async_set_updated_data = MagicMock()
    coord._rebuild_dto_caches = MagicMock()
    return coord


def _switch(coordinator, device_id: str, unique_id: str) -> SberSbermapSwitch:
    ent = next(e for e in coordinator.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapSwitch(coordinator, device_id, ent)


class TestPrimarySwitch:
    @pytest.fixture
    def entity(self, coordinator):
        return _switch(coordinator, "device_switch_1", "device_switch_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_switch_1"

    def test_name_is_none_for_primary(self, entity):
        assert entity._attr_name is None

    def test_is_on_true(self, entity):
        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_sends_on_off_true(self, entity, coordinator):
        await entity.async_turn_on()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is True for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_off_sends_on_off_false(self, entity, coordinator):
        await entity.async_turn_off()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is False for a in attrs)


class TestExtraSwitch:
    """child_lock на socket (один из mock-устройств — extra-switch со state_attribute_key)."""

    @pytest.mark.asyncio
    async def test_extra_switch_setup(self, coordinator, mock_devices_extra):
        """Smart Plug в extra-fixture имеет child_lock attribute."""
        from tests.conftest import build_coordinator_caches

        coord2 = MagicMock()
        coord2.data = mock_devices_extra
        coord2.devices, coord2.entities = build_coordinator_caches(mock_devices_extra)
        coord2.home_api = AsyncMock()
        coord2.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
        fake_client = AsyncMock()
        fake_client.devices = AsyncMock()
        coord2.home_api.get_sber_client = AsyncMock(return_value=fake_client)
        coord2.async_set_updated_data = MagicMock()
        coord2._rebuild_dto_caches = MagicMock()

        entry = MagicMock()
        entry.runtime_data = coord2
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        # Должен быть kettle_child_lock (kettle с child_lock в desired_state)
        ids = {e._attr_unique_id for e in captured}
        assert "device_kettle_1_child_lock" in ids


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_only_switch_entities(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        # mock_devices содержит switch_1 — primary on_off; других switch'ей нет.
        ids = {e._attr_unique_id for e in captured}
        assert "device_switch_1" in ids
