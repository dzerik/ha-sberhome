"""Tests for TtcSurrogateService (mocked client/coordinator/cache)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.ttc_surrogate.service import TtcSurrogateService


def _make_coord_with_home(home_id: str, home_name: str = "Test"):
    coord = MagicMock()
    coord.ttc_surrogates = {}

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


def _speaker(device_id: str = "spk-1"):
    spk = MagicMock()
    spk.id = device_id
    spk.image_set_type = "dt_boom"
    spk.full_categories = None
    return spk


async def test_hot_cache():
    coord = _make_coord_with_home("home-1")
    coord.ttc_surrogates["home-1"] = "cached-sc"
    svc = TtcSurrogateService(coord)
    assert await svc.get_surrogate_id("home-1") == "cached-sc"
    coord.client.scenarios.list.assert_not_awaited()


async def test_discover_by_marker():
    coord = _make_coord_with_home("home-1")
    coord.client.scenarios.list.return_value = [
        ScenarioDto(id="other", description="Random"),
        ScenarioDto(
            id="ttc-sc",
            description="🤖 HA TTC surrogate (sberhome): home_id=home-1",
        ),
    ]
    svc = TtcSurrogateService(coord)
    assert await svc.get_surrogate_id("home-1") == "ttc-sc"
    coord.client.scenarios.create.assert_not_awaited()


async def test_create_uses_head_dialog_task():
    coord = _make_coord_with_home("home-1", home_name="Мой дом")
    coord.state_cache.get_all_devices.return_value = {"spk-1": _speaker()}
    coord.state_cache.device_home_id = MagicMock(return_value="home-1")

    svc = TtcSurrogateService(coord)
    sid = await svc.get_surrogate_id("home-1")
    assert sid == "new-sc-id"
    body = coord.client.scenarios.create.await_args.args[0]
    assert body["home_id"] == "home-1"
    assert "Sber TTC surrogate" in body["name"]
    assert body["image"]
    task = body["steps"][0]["tasks"][0]
    assert task["type"] == "HEAD_DIALOG_COMMAND"
    assert task["head_dialog_command_task_data"]["device_id"] == "spk-1"


async def test_create_without_speakers_raises():
    from homeassistant.exceptions import HomeAssistantError

    coord = _make_coord_with_home("home-1")
    svc = TtcSurrogateService(coord)
    with pytest.raises(HomeAssistantError, match="нет колонок Sber"):
        await svc.get_surrogate_id("home-1")
    coord.client.scenarios.create.assert_not_awaited()


async def test_send_happy_path_update_then_run():
    coord = _make_coord_with_home("home-1")
    coord.ttc_surrogates["home-1"] = "cached-sc"
    svc = TtcSurrogateService(coord)

    await svc.send("home-1", "Расскажи анекдот", ["spk-1"])

    args = coord.client.scenarios.update.await_args.args
    assert args[0] == "cached-sc"
    task = args[1]["steps"][0]["tasks"][0]
    assert task["type"] == "HEAD_DIALOG_COMMAND"
    assert task["head_dialog_command_task_data"]["text"] == "Расскажи анекдот"
    assert task["head_dialog_command_task_data"]["device_id"] == "spk-1"
    coord.client.scenarios.run.assert_awaited_once_with("cached-sc")


async def test_send_multiple_speakers_multiple_tasks():
    coord = _make_coord_with_home("home-1")
    coord.ttc_surrogates["home-1"] = "cached-sc"
    svc = TtcSurrogateService(coord)

    await svc.send("home-1", "Который час", ["spk-1", "spk-2"])

    tasks = coord.client.scenarios.update.await_args.args[1]["steps"][0]["tasks"]
    assert len(tasks) == 2
    assert {t["head_dialog_command_task_data"]["device_id"] for t in tasks} == {
        "spk-1",
        "spk-2",
    }


async def test_send_no_device_ids_raises():
    from homeassistant.exceptions import HomeAssistantError

    coord = _make_coord_with_home("home-1")
    svc = TtcSurrogateService(coord)
    with pytest.raises(HomeAssistantError, match="No speakers"):
        await svc.send("home-1", "hi", [])
