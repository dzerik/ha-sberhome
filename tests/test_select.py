"""Tests for SberHome select platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.select import SberSbermapSelect, async_setup_entry
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


def _select(coordinator, device_id: str, unique_id: str) -> SberSbermapSelect:
    ent = next(e for e in coordinator.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapSelect(coordinator, device_id, ent)


class TestVacuumProgram:
    @pytest.fixture
    def entity(self, coordinator):
        return _select(coordinator, "device_vacuum_1", "device_vacuum_1_program")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_vacuum_1_program"

    def test_options(self, entity):
        assert entity._attr_options == ["perimeter", "spot", "smart"]

    def test_current_option(self, entity):
        assert entity.current_option == "smart"

    @pytest.mark.asyncio
    async def test_select_option(self, entity, coordinator):
        await entity.async_select_option("perimeter")
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(
            a.key == "vacuum_cleaner_program" and a.enum_value == "perimeter"
            for a in attrs
        )


class TestSensitivitySelect:
    def test_door_sensitivity(self, coordinator):
        entity = _select(
            coordinator, "device_door_sens_1", "device_door_sens_1_sensitivity"
        )
        assert entity._attr_options == ["auto", "high"]


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_select_entities(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._attr_unique_id for e in captured}
        assert "device_vacuum_1_program" in ids
        assert "device_door_sens_1_sensitivity" in ids
