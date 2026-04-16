"""Tests for SberHome media_player platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.media_player import MediaPlayerState

from custom_components.sberhome.media_player import (
    SberSbermapMediaPlayer,
    async_setup_entry,
)
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
def tv(coordinator):
    ent = next(
        e for e in coordinator.entities["device_tv_1"]
        if e.unique_id == "device_tv_1"
    )
    return SberSbermapMediaPlayer(coordinator, "device_tv_1", ent)


class TestTvState:
    def test_state_on(self, tv):
        assert tv.state is MediaPlayerState.ON

    def test_volume_level(self, tv):
        assert tv.volume_level == 0.40

    def test_source(self, tv):
        assert tv.source == "hdmi1"

    def test_is_volume_muted(self, tv):
        assert tv.is_volume_muted is False


class TestTvCommands:
    @pytest.mark.asyncio
    async def test_turn_on(self, tv, coordinator):
        await tv.async_turn_on()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is True for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_off(self, tv, coordinator):
        await tv.async_turn_off()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is False for a in attrs)

    @pytest.mark.asyncio
    async def test_set_volume(self, tv, coordinator):
        await tv.async_set_volume_level(0.75)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "volume_int" and a.integer_value == 75 for a in attrs)

    @pytest.mark.asyncio
    async def test_select_source(self, tv, coordinator):
        await tv.async_select_source("hdmi2")
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "source" and a.enum_value == "hdmi2" for a in attrs)

    @pytest.mark.asyncio
    async def test_send_custom_key(self, tv, coordinator):
        await tv.async_send_custom_key("home")
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "custom_key" and a.enum_value == "home" for a in attrs)

    @pytest.mark.asyncio
    async def test_play_channel(self, tv, coordinator):
        await tv.async_play_channel(5)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "channel_int" and a.integer_value == 5 for a in attrs)


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_tv(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._attr_unique_id for e in captured}
        assert "device_tv_1" in ids
