"""Tests for the SberHome media_player platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.media_player import (
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import Platform

from custom_components.sberhome.media_player import (
    SberSbermapMediaPlayer,
    async_setup_entry,
)
from custom_components.sberhome.sbermap import TV_SOURCES
from tests.conftest import build_coordinator_caches

MOCK_DEVICE_TV_ON = {
    "id": "device_tv_1",
    "serial_number": "SN_TV_001",
    "name": {"name": "Test TV"},
    "image_set_type": "tv",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-TV"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "source", "enum_value": "hdmi1"},
        {"key": "volume_int", "integer_value": 40},
        {"key": "mute", "bool_value": False},
    ],
    "attributes": [],
}

MOCK_DEVICE_TV_OFF = {
    "id": "device_tv_2",
    "serial_number": "SN_TV_002",
    "name": {"name": "Test TV Off"},
    "image_set_type": "tv",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-TV"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": False},
    ],
    "attributes": [],
}


def _make_coordinator(raw_devices: dict) -> MagicMock:
    """Coordinator-like MagicMock с sbermap-кэшами и AsyncMock на отправку команд."""
    coord = MagicMock()
    coord.data = raw_devices
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    coord.async_send_device_state = AsyncMock()
    return coord


def _player(coord, device_id: str) -> SberSbermapMediaPlayer:
    """Helper: построить SberSbermapMediaPlayer из primary MEDIA_PLAYER entity."""
    ent = next(e for e in coord.entities[device_id] if e.platform is Platform.MEDIA_PLAYER)
    return SberSbermapMediaPlayer(coord, device_id, ent)


class TestMediaPlayerState:
    """Read path: state/volume/mute/source из HaEntityData."""

    @pytest.fixture
    def coordinator(self):
        return _make_coordinator(
            {"device_tv_1": MOCK_DEVICE_TV_ON, "device_tv_2": MOCK_DEVICE_TV_OFF}
        )

    @pytest.fixture
    def entity(self, coordinator):
        return _player(coordinator, "device_tv_1")

    def test_unique_id(self, entity):
        """Primary entity — unique_id без суффикса, равен device id."""
        assert entity._attr_unique_id == "device_tv_1"

    def test_supported_features(self, entity):
        """Заявлены on/off, volume set/step/mute и выбор источника."""
        features = entity.supported_features
        assert features & MediaPlayerEntityFeature.TURN_ON
        assert features & MediaPlayerEntityFeature.TURN_OFF
        assert features & MediaPlayerEntityFeature.VOLUME_SET
        assert features & MediaPlayerEntityFeature.VOLUME_STEP
        assert features & MediaPlayerEntityFeature.VOLUME_MUTE
        assert features & MediaPlayerEntityFeature.SELECT_SOURCE

    def test_state_on(self, entity):
        """reported on_off=true → MediaPlayerState.ON."""
        assert entity.state is MediaPlayerState.ON

    def test_state_off(self, coordinator):
        """reported on_off=false → MediaPlayerState.OFF."""
        assert _player(coordinator, "device_tv_2").state is MediaPlayerState.OFF

    def test_volume_level(self, entity):
        """volume_int=40 (0-100) → volume_level=0.4 (0-1)."""
        assert entity.volume_level == pytest.approx(0.4)

    def test_is_volume_muted(self, entity):
        """mute=false → is_volume_muted=False."""
        assert entity.is_volume_muted is False

    def test_source(self, entity):
        """reported source → текущий источник."""
        assert entity.source == "hdmi1"

    def test_source_list(self, entity):
        """source_list берётся из статического TV_SOURCES."""
        assert entity.source_list == list(TV_SOURCES)

    def test_attributes_none_when_not_reported(self, coordinator):
        """У выключенного TV нет volume/mute/source в reported — все None."""
        entity = _player(coordinator, "device_tv_2")
        assert entity.volume_level is None
        assert entity.is_volume_muted is None
        assert entity.source is None

    def test_state_none_when_entity_disappears(self, coordinator, entity):
        """Устройство пропало из entities-кэша → state и атрибуты None."""
        coordinator.entities["device_tv_1"] = []
        assert entity.state is None
        assert entity.volume_level is None
        assert entity.is_volume_muted is None
        assert entity.source is None


class TestMediaPlayerCommands:
    """Write path: команды строятся sbermap-билдерами и уходят координатору."""

    @pytest.fixture
    def coordinator(self):
        return _make_coordinator({"device_tv_1": MOCK_DEVICE_TV_ON})

    @pytest.fixture
    def entity(self, coordinator):
        return _player(coordinator, "device_tv_1")

    def _sent(self, coordinator) -> tuple[str, dict]:
        coordinator.async_send_device_state.assert_awaited_once()
        device_id, attrs = coordinator.async_send_device_state.await_args.args
        return device_id, {a.key: a for a in attrs}

    async def test_turn_on(self, coordinator, entity):
        """async_turn_on → on_off=true для правильного device_id."""
        await entity.async_turn_on()
        device_id, sent = self._sent(coordinator)
        assert device_id == "device_tv_1"
        assert sent["on_off"].bool_value is True

    async def test_turn_off(self, coordinator, entity):
        """async_turn_off → on_off=false."""
        await entity.async_turn_off()
        _, sent = self._sent(coordinator)
        assert sent["on_off"].bool_value is False

    async def test_set_volume_level(self, coordinator, entity):
        """HA volume 0.55 (0-1) конвертируется в volume_int=55 (0-100)."""
        await entity.async_set_volume_level(0.55)
        _, sent = self._sent(coordinator)
        assert sent["volume_int"].integer_value == 55

    async def test_volume_up(self, coordinator, entity):
        """volume_up → direction='+'."""
        await entity.async_volume_up()
        _, sent = self._sent(coordinator)
        assert sent["direction"].enum_value == "+"

    async def test_volume_down(self, coordinator, entity):
        """volume_down → direction='-'."""
        await entity.async_volume_down()
        _, sent = self._sent(coordinator)
        assert sent["direction"].enum_value == "-"

    async def test_mute_volume(self, coordinator, entity):
        """mute → bool_value=true в ключе mute."""
        await entity.async_mute_volume(True)
        _, sent = self._sent(coordinator)
        assert sent["mute"].bool_value is True

    async def test_select_source(self, coordinator, entity):
        """select_source → enum source."""
        await entity.async_select_source("hdmi2")
        _, sent = self._sent(coordinator)
        assert sent["source"].enum_value == "hdmi2"

    async def test_send_custom_key(self, coordinator, entity):
        """Кастомный сервис send_custom_key → enum custom_key."""
        await entity.async_send_custom_key("back")
        _, sent = self._sent(coordinator)
        assert sent["custom_key"].enum_value == "back"

    async def test_send_direction(self, coordinator, entity):
        """Кастомный сервис send_direction → enum direction."""
        await entity.async_send_direction("up")
        _, sent = self._sent(coordinator)
        assert sent["direction"].enum_value == "up"

    async def test_play_channel(self, coordinator, entity):
        """Кастомный сервис play_channel → integer channel_int."""
        await entity.async_play_channel(5)
        _, sent = self._sent(coordinator)
        assert sent["channel_int"].integer_value == 5


class TestAsyncSetupEntry:
    async def test_creates_only_media_player_entities(self):
        """setup_entry создаёт по одному media_player на каждый TV.

        Вне platform-контекста async_get_current_platform кидает
        RuntimeError — setup должен молча пропустить регистрацию сервисов.
        """
        coordinator = _make_coordinator(
            {"device_tv_1": MOCK_DEVICE_TV_ON, "device_tv_2": MOCK_DEVICE_TV_OFF}
        )
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        assert len(captured) == 2
        assert all(isinstance(e, SberSbermapMediaPlayer) for e in captured)

    async def test_registers_entity_services_in_platform_context(self):
        """Внутри platform-контекста регистрируются 3 кастомных сервиса."""
        coordinator = _make_coordinator({"device_tv_1": MOCK_DEVICE_TV_ON})
        entry = MagicMock()
        entry.runtime_data = coordinator
        platform = MagicMock()
        with patch(
            "custom_components.sberhome.media_player.entity_platform.async_get_current_platform",
            return_value=platform,
        ):
            await async_setup_entry(MagicMock(), entry, lambda _: None)

        registered = {
            call.args[0] for call in platform.async_register_entity_service.call_args_list
        }
        assert registered == {"send_custom_key", "send_direction", "play_channel"}
