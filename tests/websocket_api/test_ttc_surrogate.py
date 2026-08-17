"""Tests for sberhome/ttc_surrogate/* WS endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.websocket_api.ttc_surrogate import (
    ws_ensure_ttc_surrogate,
    ws_status_ttc_surrogate,
    ws_test_ttc_surrogate,
)


def _make_hass_with_coord(homes, devices=None, surrogates=None, sber_scenarios=None):
    coord = MagicMock()
    coord.state_cache.get_homes.return_value = homes
    coord.state_cache.get_all_devices.return_value = devices or {}
    coord.state_cache.device_home_id = MagicMock(return_value=None)
    coord.ttc_surrogates = surrogates or {}
    coord.ttc_service.get_surrogate_id = AsyncMock(return_value="new-sc-id")
    coord.ttc_service.send = AsyncMock()
    coord.client.scenarios.list = AsyncMock(return_value=sber_scenarios or [])

    hass = MagicMock()
    hass.data = {"sberhome": {}}
    entry = MagicMock()
    entry.runtime_data = coord
    hass.config_entries.async_loaded_entries.return_value = [entry]
    return hass, coord


@pytest.mark.asyncio
async def test_status_discovers_ttc_surrogate_by_marker():
    home = MagicMock()
    home.id = "home-1"
    home.name = "Мой дом"
    hass, coord = _make_hass_with_coord(
        homes=[home],
        sber_scenarios=[
            ScenarioDto(
                id="ttc-sc",
                description="🤖 HA TTC surrogate (sberhome): home_id=home-1",
            ),
        ],
    )
    connection = MagicMock()
    await ws_status_ttc_surrogate.__wrapped__(
        hass, connection, {"id": 1, "type": "sberhome/ttc_surrogate/status"}
    )
    result = connection.send_result.call_args.args[1]
    assert result["homes"][0]["scenario_id"] == "ttc-sc"
    assert coord.ttc_surrogates["home-1"] == "ttc-sc"


@pytest.mark.asyncio
async def test_status_ignores_tts_surrogate():
    """TTC-status НЕ должен подхватить TTS-surrogate того же дома."""
    home = MagicMock()
    home.id = "home-1"
    home.name = "Дом"
    hass, coord = _make_hass_with_coord(
        homes=[home],
        sber_scenarios=[
            ScenarioDto(id="tts-sc", name="Sber TTS surrogate (Дом) [home_id=home-1]"),
        ],
    )
    connection = MagicMock()
    await ws_status_ttc_surrogate.__wrapped__(
        hass, connection, {"id": 1, "type": "sberhome/ttc_surrogate/status"}
    )
    result = connection.send_result.call_args.args[1]
    assert result["homes"][0]["scenario_id"] is None


@pytest.mark.asyncio
async def test_ensure_calls_service():
    home = MagicMock()
    home.id = "home-1"
    home.name = "Дом"
    hass, coord = _make_hass_with_coord(homes=[home])
    connection = MagicMock()
    await ws_ensure_ttc_surrogate.__wrapped__(
        hass, connection, {"id": 1, "type": "sberhome/ttc_surrogate/ensure", "home_id": "home-1"}
    )
    coord.ttc_service.get_surrogate_id.assert_awaited_once_with("home-1")
    result = connection.send_result.call_args.args[1]
    assert result["ok"] is True
    assert result["scenario_id"] == "new-sc-id"


@pytest.mark.asyncio
async def test_test_calls_send_with_command_and_latency():
    home = MagicMock()
    home.id = "home-1"
    home.name = "Дом"
    hass, coord = _make_hass_with_coord(homes=[home])
    connection = MagicMock()
    await ws_test_ttc_surrogate.__wrapped__(
        hass,
        connection,
        {
            "id": 1,
            "type": "sberhome/ttc_surrogate/test",
            "home_id": "home-1",
            "message": "Расскажи анекдот",
            "device_ids": ["spk-1"],
        },
    )
    coord.ttc_service.send.assert_awaited_once_with("home-1", "Расскажи анекдот", ["spk-1"])
    result = connection.send_result.call_args.args[1]
    assert result["ok"] is True
    assert "latency_ms" in result
