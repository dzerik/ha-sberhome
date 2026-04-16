"""Tests for SberHome number platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.number import SberSbermapNumber, async_setup_entry
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


def _number(coordinator, device_id: str, unique_id: str) -> SberSbermapNumber:
    ent = next(e for e in coordinator.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapNumber(coordinator, device_id, ent)


class TestKettleTargetTemperature:
    @pytest.fixture
    def entity(self, coordinator):
        return _number(
            coordinator, "device_kettle_1", "device_kettle_1_target_temperature"
        )

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_kettle_1_target_temperature"

    def test_min_max_step(self, entity):
        assert entity._attr_native_min_value == 60
        assert entity._attr_native_max_value == 100
        assert entity._attr_native_step == 10

    def test_native_value(self, entity):
        assert entity.native_value == 80.0

    @pytest.mark.asyncio
    async def test_set_native_value(self, entity, coordinator):
        await entity.async_set_native_value(90)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(
            a.key == "kitchen_water_temperature_set" and a.integer_value == 90
            for a in attrs
        )


class TestACTargetHumidity:
    def test_humidity_number_present(self, coordinator):
        ents = coordinator.entities["device_hvac_ac_1"]
        target_h = next(
            (e for e in ents if e.unique_id == "device_hvac_ac_1_target_humidity"),
            None,
        )
        assert target_h is not None
        assert target_h.state == 50.0


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_numbers(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._attr_unique_id for e in captured}
        assert "device_kettle_1_target_temperature" in ids
        assert "device_hvac_ac_1_target_humidity" in ids
