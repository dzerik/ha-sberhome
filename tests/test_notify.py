"""Tests for SberHome notify platform (TTS surrogate)."""

from unittest.mock import AsyncMock, MagicMock

from custom_components.sberhome.notify import SberHomeTtsNotify


def _make_coord(homes):
    coord = MagicMock()
    coord.state_cache.get_homes.return_value = homes
    coord.tts_service = MagicMock()
    coord.tts_service.send = AsyncMock()
    return coord


def _home(home_id: str, name: str):
    h = MagicMock()
    h.id = home_id
    h.name = name
    return h


async def test_notify_entity_basic_attrs():
    home = _home("home-1", "Мой дом")
    coord = _make_coord([home])
    entity = SberHomeTtsNotify(coord, coord.tts_service, home)
    assert entity.unique_id == "sber_tts_home-1"
    assert entity.name == "Sber TTS (Мой дом)"
    assert entity.device_info["identifiers"] == {("sberhome", "home:home-1")}


async def test_notify_send_message_calls_tts_service():
    home = _home("home-1", "Мой дом")
    coord = _make_coord([home])
    entity = SberHomeTtsNotify(coord, coord.tts_service, home)
    await entity.async_send_message("Привет")
    coord.tts_service.send.assert_awaited_once_with("home-1", "Привет", None)


async def test_notify_send_message_with_data_device_ids():
    """data.device_ids override → передаётся в TtsSurrogateService.send."""
    home = _home("home-1", "X")
    coord = _make_coord([home])
    entity = SberHomeTtsNotify(coord, coord.tts_service, home)
    await entity.async_send_message(
        "hi",
        data={"device_ids": ["spk-A", "spk-B"]},
    )
    coord.tts_service.send.assert_awaited_once_with("home-1", "hi", ["spk-A", "spk-B"])


async def test_notify_send_message_with_target_logs_warning_in_v560():
    """v5.6.0 не реализует target-resolution (HA entity_id → Sber device_id).
    target передаётся как None в TTS service. Warning логируется."""
    home = _home("home-1", "X")
    coord = _make_coord([home])
    entity = SberHomeTtsNotify(coord, coord.tts_service, home)
    await entity.async_send_message(
        "hi",
        target=["media_player.kitchen"],
    )
    # target игнорируется → device_ids=None → fallback на all home speakers
    coord.tts_service.send.assert_awaited_once_with("home-1", "hi", None)
