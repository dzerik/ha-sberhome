"""Tests for TtsSurrogateService (mocked client/coordinator/cache)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.tts_surrogate.service import (
    SBER_SPEAKER_CATEGORY,  # noqa: F401  # imported to assert symbol exists
    TtsSurrogateService,
)


def _make_coord_with_home(home_id: str, home_name: str = "Test"):
    """Минимальный coordinator-stub с одним домом и набором devices."""
    coord = MagicMock()
    coord.tts_surrogates = {}

    home_dto = MagicMock()
    home_dto.id = home_id
    home_dto.name = home_name
    coord.state_cache.get_homes.return_value = [home_dto]

    coord.client.scenarios.list = AsyncMock(return_value=[])
    coord.client.scenarios.create = AsyncMock(return_value={"id": "new-sc-id"})
    coord.client.scenarios.update = AsyncMock(return_value={"id": "any"})
    coord.client.scenarios.run = AsyncMock(return_value={"ok": True})

    coord.state_cache.get_all_devices.return_value = {}
    coord.state_cache.device_home_id = MagicMock(return_value=None)
    return coord


async def test_get_surrogate_id_hot_cache():
    coord = _make_coord_with_home("home-1")
    coord.tts_surrogates["home-1"] = "cached-sc"
    svc = TtsSurrogateService(coord)
    sid = await svc.get_surrogate_id("home-1")
    assert sid == "cached-sc"
    coord.client.scenarios.list.assert_not_awaited()
    coord.client.scenarios.create.assert_not_awaited()


async def test_get_surrogate_id_list_match_by_marker():
    coord = _make_coord_with_home("home-1")
    coord.client.scenarios.list.return_value = [
        ScenarioDto(id="other-sc", description="Random"),
        ScenarioDto(
            id="surrogate-sc",
            description="🤖 HA TTS surrogate (sberhome): home_id=home-1",
        ),
    ]
    svc = TtsSurrogateService(coord)
    sid = await svc.get_surrogate_id("home-1")
    assert sid == "surrogate-sc"
    assert coord.tts_surrogates["home-1"] == "surrogate-sc"
    coord.client.scenarios.create.assert_not_awaited()


async def test_get_surrogate_id_create_when_no_match():
    """Create требует non-empty speakers — Sber отказывает в пустых tasks."""
    coord = _make_coord_with_home("home-1", home_name="Мой дом")
    coord.client.scenarios.list.return_value = []

    # Speakers нужны для create (placeholder phrase + real device_ids).
    spk = MagicMock()
    spk.id = "spk-1"
    spk.image_set_type = "dt_boom"
    spk.full_categories = None
    coord.state_cache.get_all_devices.return_value = {"spk-1": spk}
    coord.state_cache.device_home_id = MagicMock(return_value="home-1")

    svc = TtsSurrogateService(coord)
    sid = await svc.get_surrogate_id("home-1")
    assert sid == "new-sc-id"
    coord.client.scenarios.create.assert_awaited_once()
    body = coord.client.scenarios.create.await_args.args[0]
    assert body["home_id"] == "home-1"
    assert "Мой дом" in body["name"]
    # image обязателен для Sber API (см. intents.encoder.DEFAULT_IMAGE).
    assert body["image"], "image field обязателен для Sber API"
    # Guard phrase: Sber отказывает в conditions:[] (HTTP 500 "bad nested
    # condition") и фильтрует non-Cyrillic phrases. Используем русскую
    # placeholder-фразу — юзер не произнесёт её в обиходе.
    inner = body["steps"][0]["condition"]["nested_conditions_data"]["conditions"]
    assert len(inner) == 1
    assert inner[0]["type"] == "PHRASES"
    guard = inner[0]["phrases_data"]["phrases"][0]
    # Только Cyrillic + пробелы — Sber STT отвергает другие алфавиты.
    assert all(ch.isspace() or "а" <= ch.lower() <= "я" or ch == "ё" for ch in guard), (
        f"Guard phrase must be Cyrillic-only, got: {guard!r}"
    )
    # PRONOUNCE_COMMAND task с real device_id (Sber требует non-empty).
    pd = body["steps"][0]["tasks"][0]["pronounce_data"]
    assert pd["device_ids"] == ["spk-1"]
    assert coord.tts_surrogates["home-1"] == "new-sc-id"


async def test_get_surrogate_id_create_without_speakers_raises():
    """No speakers в доме → cannot create (Sber отвергнет пустые tasks)."""
    from homeassistant.exceptions import HomeAssistantError

    coord = _make_coord_with_home("home-1")
    coord.client.scenarios.list.return_value = []
    # get_all_devices пуст по умолчанию из _make_coord_with_home.

    svc = TtsSurrogateService(coord)
    with pytest.raises(HomeAssistantError, match="нет колонок Sber"):
        await svc.get_surrogate_id("home-1")

    coord.client.scenarios.create.assert_not_awaited()


async def test_send_happy_path_calls_update_then_run():
    coord = _make_coord_with_home("home-1")
    coord.tts_surrogates["home-1"] = "cached-sc"
    svc = TtsSurrogateService(coord)

    await svc.send("home-1", "Привет", ["spk-1"])

    coord.client.scenarios.update.assert_awaited_once()
    args = coord.client.scenarios.update.await_args.args
    assert args[0] == "cached-sc"
    body = args[1]
    pd = body["steps"][0]["tasks"][0]["pronounce_data"]
    assert pd["phrase"] == "Привет"
    assert pd["device_ids"] == ["spk-1"]

    coord.client.scenarios.run.assert_awaited_once_with("cached-sc")


async def test_send_no_device_ids_raises_home_assistant_error():
    from homeassistant.exceptions import HomeAssistantError

    coord = _make_coord_with_home("home-1")
    coord.tts_surrogates["home-1"] = "cached-sc"
    svc = TtsSurrogateService(coord)

    with pytest.raises(HomeAssistantError, match="No speakers"):
        await svc.send("home-1", "hi", [])

    coord.client.scenarios.update.assert_not_awaited()


async def test_send_falls_back_to_all_speakers_when_device_ids_none():
    coord = _make_coord_with_home("home-1")
    coord.tts_surrogates["home-1"] = "cached-sc"

    spk = MagicMock()
    spk.id = "speaker-1"
    spk.image_set_type = "dt_boom"
    spk.full_categories = None
    coord.state_cache.get_all_devices.return_value = {"speaker-1": spk}
    coord.state_cache.device_home_id = MagicMock(
        side_effect=lambda dev_id: "home-1" if dev_id == "speaker-1" else None
    )

    svc = TtsSurrogateService(coord)
    await svc.send("home-1", "Привет", None)

    coord.client.scenarios.update.assert_awaited_once()
    body = coord.client.scenarios.update.await_args.args[1]
    pd = body["steps"][0]["tasks"][0]["pronounce_data"]
    assert pd["device_ids"] == ["speaker-1"]


async def test_send_skips_non_speaker_devices_in_home():
    coord = _make_coord_with_home("home-1")
    coord.tts_surrogates["home-1"] = "cached-sc"

    spk = MagicMock()
    spk.id = "spk-1"
    spk.image_set_type = "dt_boom"
    spk.full_categories = None
    lamp = MagicMock()
    lamp.id = "lamp-1"
    lamp.image_set_type = "cat_bulb_m"
    lamp.full_categories = None
    coord.state_cache.get_all_devices.return_value = {"spk-1": spk, "lamp-1": lamp}
    coord.state_cache.device_home_id = MagicMock(side_effect=lambda dev_id: "home-1")

    svc = TtsSurrogateService(coord)
    await svc.send("home-1", "hi", None)

    body = coord.client.scenarios.update.await_args.args[1]
    pd = body["steps"][0]["tasks"][0]["pronounce_data"]
    assert pd["device_ids"] == ["spk-1"]
    assert "lamp-1" not in pd["device_ids"]


async def test_send_404_on_update_triggers_recreate_and_retry():
    from custom_components.sberhome.exceptions import SberApiError

    coord = _make_coord_with_home("home-1")
    coord.tts_surrogates["home-1"] = "stale-sc-id"

    # Recreate path тоже использует _all_speakers_in_home — нужен speaker.
    spk = MagicMock()
    spk.id = "spk-1"
    spk.image_set_type = "dt_boom"
    spk.full_categories = None
    coord.state_cache.get_all_devices.return_value = {"spk-1": spk}
    coord.state_cache.device_home_id = MagicMock(return_value="home-1")

    err_404 = SberApiError(code=0, status_code=404, message="not found")
    coord.client.scenarios.update = AsyncMock(side_effect=[err_404, {"ok": True}])
    coord.client.scenarios.list = AsyncMock(return_value=[])
    coord.client.scenarios.create = AsyncMock(return_value={"id": "new-sc"})

    svc = TtsSurrogateService(coord)
    await svc.send("home-1", "retry", ["spk-1"])

    assert coord.client.scenarios.update.await_count == 2
    assert coord.tts_surrogates["home-1"] == "new-sc"
    coord.client.scenarios.create.assert_awaited_once()
    coord.client.scenarios.run.assert_awaited_once_with("new-sc")
