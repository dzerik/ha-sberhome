"""Tests for SberHome button platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.button import SberSbermapButton, async_setup_entry
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


def _btn(coordinator, device_id: str, unique_id: str) -> SberSbermapButton:
    ent = next(e for e in coordinator.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapButton(coordinator, device_id, ent)


class TestIntercomUnlock:
    @pytest.fixture
    def entity(self, coordinator):
        return _btn(coordinator, "device_intercom_1", "device_intercom_1_unlock")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "device_intercom_1_unlock"

    def test_icon(self, entity):
        assert entity._attr_icon == "mdi:door-open"

    @pytest.mark.asyncio
    async def test_press_sends_bool_true(self, entity, coordinator):
        await entity.async_press()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "unlock" and a.bool_value is True for a in attrs)


class TestIntercomReject:
    @pytest.fixture
    def entity(self, coordinator):
        return _btn(coordinator, "device_intercom_1", "device_intercom_1_reject_call")

    def test_icon(self, entity):
        assert entity._attr_icon == "mdi:phone-hangup"


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_intercom_buttons(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._attr_unique_id for e in captured}
        assert "device_intercom_1_unlock" in ids
        assert "device_intercom_1_reject_call" in ids
