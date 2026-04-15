"""Tests for the SberHome media_player (TV) platform."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)

from custom_components.sberhome.media_player import (
    SberTvEntity,
    async_setup_entry,
)
from custom_components.sberhome.registry import CATEGORY_MEDIA_PLAYERS


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.fixture
def tv_entity(coordinator):
    return SberTvEntity(coordinator, "device_tv_1", CATEGORY_MEDIA_PLAYERS["tv"])


class TestSberTvEntity:
    def test_unique_id(self, tv_entity):
        assert tv_entity._attr_unique_id == "device_tv_1"

    def test_name(self, tv_entity):
        assert tv_entity._attr_name is None

    def test_supported_features(self, tv_entity):
        sf = tv_entity._attr_supported_features
        assert sf & MediaPlayerEntityFeature.TURN_ON
        assert sf & MediaPlayerEntityFeature.TURN_OFF
        assert sf & MediaPlayerEntityFeature.VOLUME_SET
        assert sf & MediaPlayerEntityFeature.VOLUME_STEP
        assert sf & MediaPlayerEntityFeature.VOLUME_MUTE
        assert sf & MediaPlayerEntityFeature.SELECT_SOURCE

    def test_source_list(self, tv_entity):
        assert tv_entity._attr_source_list == ["hdmi1", "hdmi2", "hdmi3", "tv", "av", "content"]

    def test_state_on(self, tv_entity):
        assert tv_entity.state == MediaPlayerState.ON

    def test_state_off(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_tv_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": False}]
        coordinator.data["device_tv_1"] = dev
        entity = SberTvEntity(coordinator, "device_tv_1", CATEGORY_MEDIA_PLAYERS["tv"])
        assert entity.state == MediaPlayerState.OFF

    def test_state_off_no_on_off(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_tv_1"])
        dev["desired_state"] = []
        coordinator.data["device_tv_1"] = dev
        entity = SberTvEntity(coordinator, "device_tv_1", CATEGORY_MEDIA_PLAYERS["tv"])
        assert entity.state == MediaPlayerState.OFF

    def test_volume_level(self, tv_entity):
        # 40 / 100 = 0.4
        assert tv_entity.volume_level == 0.4

    def test_volume_level_none(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_tv_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": True}]
        coordinator.data["device_tv_1"] = dev
        entity = SberTvEntity(coordinator, "device_tv_1", CATEGORY_MEDIA_PLAYERS["tv"])
        assert entity.volume_level is None

    def test_is_volume_muted_false(self, tv_entity):
        assert tv_entity.is_volume_muted is False

    def test_is_volume_muted_true(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_tv_1"])
        dev["desired_state"] = [
            {"key": "on_off", "bool_value": True},
            {"key": "mute", "bool_value": True},
        ]
        coordinator.data["device_tv_1"] = dev
        entity = SberTvEntity(coordinator, "device_tv_1", CATEGORY_MEDIA_PLAYERS["tv"])
        assert entity.is_volume_muted is True

    def test_source(self, tv_entity):
        assert tv_entity.source == "hdmi1"

    def test_source_none(self, coordinator, mock_devices_extra):
        dev = dict(mock_devices_extra["device_tv_1"])
        dev["desired_state"] = [{"key": "on_off", "bool_value": True}]
        coordinator.data["device_tv_1"] = dev
        entity = SberTvEntity(coordinator, "device_tv_1", CATEGORY_MEDIA_PLAYERS["tv"])
        assert entity.source is None

    @pytest.mark.asyncio
    async def test_turn_on(self, tv_entity, coordinator):
        await tv_entity.async_turn_on()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_tv_1", [{"key": "on_off", "bool_value": True}]
        )

    @pytest.mark.asyncio
    async def test_turn_off(self, tv_entity, coordinator):
        await tv_entity.async_turn_off()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_tv_1", [{"key": "on_off", "bool_value": False}]
        )

    @pytest.mark.asyncio
    async def test_set_volume_level(self, tv_entity, coordinator):
        await tv_entity.async_set_volume_level(0.5)
        # 0.5 * 100 = 50
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_tv_1", [{"key": "volume_int", "integer_value": 50}]
        )

    @pytest.mark.asyncio
    async def test_volume_up(self, tv_entity, coordinator):
        await tv_entity.async_volume_up()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_tv_1", [{"key": "direction", "enum_value": "+"}]
        )

    @pytest.mark.asyncio
    async def test_volume_down(self, tv_entity, coordinator):
        await tv_entity.async_volume_down()
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_tv_1", [{"key": "direction", "enum_value": "-"}]
        )

    @pytest.mark.asyncio
    async def test_mute_volume(self, tv_entity, coordinator):
        await tv_entity.async_mute_volume(True)
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_tv_1", [{"key": "mute", "bool_value": True}]
        )

    @pytest.mark.asyncio
    async def test_select_source(self, tv_entity, coordinator):
        await tv_entity.async_select_source("hdmi2")
        coordinator.home_api.set_device_state.assert_called_once_with(
            "device_tv_1", [{"key": "source", "enum_value": "hdmi2"}]
        )
        coordinator.async_set_updated_data.assert_called_once()


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_tv_entities(self, mock_devices_extra):
        coordinator = MagicMock()
        coordinator.data = mock_devices_extra
        entry = MagicMock()
        entry.runtime_data = coordinator

        entities = []
        await async_setup_entry(MagicMock(), entry, entities.extend)
        assert len(entities) == 1
        assert entities[0]._device_id == "device_tv_1"
