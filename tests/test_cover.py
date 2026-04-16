"""Tests for SberHome cover platform — sbermap-driven (PR #5)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverDeviceClass,
    CoverEntityFeature,
)

from custom_components.sberhome.cover import SberSbermapCover, async_setup_entry
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


def _cover(coordinator, device_id: str, unique_id: str) -> SberSbermapCover:
    ent = next(e for e in coordinator.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapCover(coordinator, device_id, ent)


class TestCurtain:
    @pytest.fixture
    def curtain(self, coordinator):
        return _cover(coordinator, "device_curtain_1", "device_curtain_1")

    def test_unique_id(self, curtain):
        assert curtain._attr_unique_id == "device_curtain_1"

    def test_device_class(self, curtain):
        assert curtain._attr_device_class is CoverDeviceClass.CURTAIN

    def test_supported_features(self, curtain):
        sf = curtain._attr_supported_features
        assert sf & CoverEntityFeature.OPEN
        assert sf & CoverEntityFeature.CLOSE
        assert sf & CoverEntityFeature.STOP
        assert sf & CoverEntityFeature.SET_POSITION

    def test_current_cover_position(self, curtain):
        assert curtain.current_cover_position == 70

    def test_is_closed_open(self, curtain):
        assert curtain.is_closed is False

    @pytest.mark.asyncio
    async def test_open_cover(self, curtain, coordinator):
        await curtain.async_open_cover()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "open_set" and a.integer_value == 100 for a in attrs)

    @pytest.mark.asyncio
    async def test_close_cover(self, curtain, coordinator):
        await curtain.async_close_cover()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "open_set" and a.integer_value == 0 for a in attrs)

    @pytest.mark.asyncio
    async def test_set_position(self, curtain, coordinator):
        await curtain.async_set_cover_position(**{ATTR_POSITION: 42})
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "open_set" and a.integer_value == 42 for a in attrs)

    @pytest.mark.asyncio
    async def test_stop(self, curtain, coordinator):
        await curtain.async_stop_cover()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "open_state" and a.enum_value == "stop" for a in attrs)


class TestGate:
    @pytest.fixture
    def gate(self, coordinator):
        return _cover(coordinator, "device_gate_1", "device_gate_1")

    def test_device_class(self, gate):
        assert gate._attr_device_class is CoverDeviceClass.GATE

    def test_is_closed_true(self, gate):
        assert gate.is_closed is True


class TestValveNoStopOrPosition:
    """Valve config — supports_set_position=False, supports_stop=False."""

    def test_valve_features(self, coordinator):
        # Mocks не содержат valve, проверяем через config напрямую.
        from custom_components.sberhome.sbermap import cover_config_for

        cfg = cover_config_for("valve")
        assert cfg.supports_set_position is False
        assert cfg.supports_stop is False


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_3_covers(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._device_id for e in captured}
        assert ids == {"device_curtain_1", "device_gate_1", "device_blind_1"}

    @pytest.mark.asyncio
    async def test_no_covers_for_unrelated(self, mock_coordinator_with_entities):
        entry = MagicMock()
        entry.runtime_data = mock_coordinator_with_entities
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        assert captured == []
