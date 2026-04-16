"""Tests for SberHome vacuum platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.vacuum import VacuumActivity

from custom_components.sberhome.vacuum import SberSbermapVacuum, async_setup_entry
from tests.conftest import build_coordinator_caches


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.devices, coord.entities = build_coordinator_caches(mock_devices_extra)
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    fake_client = AsyncMock()
    fake_client.devices = AsyncMock()
    coord.home_api.get_sber_client = AsyncMock(return_value=fake_client)
    coord._fake_client = fake_client
    coord.async_set_updated_data = MagicMock()
    coord._rebuild_dto_caches = MagicMock()
    return coord


@pytest.fixture
def vacuum(coordinator):
    ent = next(
        e for e in coordinator.entities["device_vacuum_1"]
        if e.unique_id == "device_vacuum_1"
    )
    return SberSbermapVacuum(coordinator, "device_vacuum_1", ent)


class TestVacuumState:
    def test_unique_id(self, vacuum):
        assert vacuum._attr_unique_id == "device_vacuum_1"

    def test_activity_cleaning(self, vacuum):
        assert vacuum.activity is VacuumActivity.CLEANING

    def test_battery_level(self, vacuum):
        assert vacuum.battery_level == 67


class TestVacuumCommands:
    @pytest.mark.asyncio
    async def test_start(self, vacuum, coordinator):
        await vacuum.async_start()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(
            a.key == "vacuum_cleaner_command" and a.enum_value == "start"
            for a in attrs
        )

    @pytest.mark.asyncio
    async def test_pause(self, vacuum, coordinator):
        await vacuum.async_pause()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.enum_value == "pause" for a in attrs)

    @pytest.mark.asyncio
    async def test_return_to_base(self, vacuum, coordinator):
        await vacuum.async_return_to_base()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.enum_value == "return_to_base" for a in attrs)

    @pytest.mark.asyncio
    async def test_locate(self, vacuum, coordinator):
        await vacuum.async_locate()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.enum_value == "locate" for a in attrs)


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_vacuum(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._attr_unique_id for e in captured}
        assert "device_vacuum_1" in ids
