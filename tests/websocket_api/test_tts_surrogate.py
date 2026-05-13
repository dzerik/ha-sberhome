"""Tests for sberhome/tts_surrogate/* WS endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.websocket_api.tts_surrogate import (
    ws_ensure_tts_surrogate,
    ws_status_tts_surrogate,
    ws_test_tts_surrogate,
)


def _make_hass_with_coord(homes, devices=None, surrogates=None):
    coord = MagicMock()
    coord.state_cache.get_homes.return_value = homes
    coord.state_cache.get_all_devices.return_value = devices or {}
    coord.state_cache.device_home_id = MagicMock(return_value=None)
    coord.tts_surrogates = surrogates or {}
    coord.tts_service.get_surrogate_id = AsyncMock(return_value="new-sc-id")
    coord.tts_service.send = AsyncMock()
    coord.client.scenarios.create = AsyncMock(return_value={"id": "any"})

    hass = MagicMock()
    hass.data = {"sberhome": {}}
    entry = MagicMock()
    entry.runtime_data = coord
    hass.config_entries.async_loaded_entries.return_value = [entry]
    return hass, coord


@pytest.mark.asyncio
async def test_status_returns_homes_with_surrogate_state():
    home = MagicMock()
    home.id = "home-1"
    home.name = "Мой дом"
    hass, coord = _make_hass_with_coord(
        homes=[home],
        surrogates={"home-1": "sc-cached"},
    )
    connection = MagicMock()
    msg = {"id": 1, "type": "sberhome/tts_surrogate/status"}
    await ws_status_tts_surrogate.__wrapped__(hass, connection, msg)
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args.args[1]
    assert len(result["homes"]) == 1
    h = result["homes"][0]
    assert h["home_id"] == "home-1"
    assert h["name"] == "Мой дом"
    assert h["scenario_id"] == "sc-cached"


@pytest.mark.asyncio
async def test_status_no_entry_returns_empty_homes():
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_loaded_entries.return_value = []
    connection = MagicMock()
    await ws_status_tts_surrogate.__wrapped__(hass, connection, {"id": 1, "type": "x"})
    connection.send_result.assert_called_once()
    assert connection.send_result.call_args.args[1] == {"homes": []}


@pytest.mark.asyncio
async def test_ensure_creates_surrogate_when_missing():
    home = MagicMock()
    home.id = "home-1"
    home.name = "X"
    hass, coord = _make_hass_with_coord(homes=[home])
    connection = MagicMock()
    msg = {"id": 7, "type": "sberhome/tts_surrogate/ensure", "home_id": "home-1"}
    await ws_ensure_tts_surrogate.__wrapped__(hass, connection, msg)
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args.args[1]
    assert result["ok"] is True
    assert result["scenario_id"] == "new-sc-id"


@pytest.mark.asyncio
async def test_test_endpoint_runs_send_and_measures_latency():
    home = MagicMock()
    home.id = "home-1"
    home.name = "X"
    hass, coord = _make_hass_with_coord(homes=[home])
    connection = MagicMock()
    msg = {
        "id": 9,
        "type": "sberhome/tts_surrogate/test",
        "home_id": "home-1",
        "message": "Привет",
        "device_ids": ["spk-1"],
    }
    await ws_test_tts_surrogate.__wrapped__(hass, connection, msg)
    coord.tts_service.send.assert_awaited_once_with("home-1", "Привет", ["spk-1"])
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args.args[1]
    assert result["ok"] is True
    assert "latency_ms" in result


@pytest.mark.asyncio
async def test_test_endpoint_returns_error_on_exception():
    home = MagicMock()
    home.id = "home-1"
    home.name = "X"
    hass, coord = _make_hass_with_coord(homes=[home])
    coord.tts_service.send = AsyncMock(side_effect=RuntimeError("Sber unavailable"))
    connection = MagicMock()
    msg = {
        "id": 10,
        "type": "sberhome/tts_surrogate/test",
        "home_id": "home-1",
        "message": "x",
    }
    await ws_test_tts_surrogate.__wrapped__(hass, connection, msg)
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args.args[1]
    assert result["ok"] is False
    assert "Sber unavailable" in result["error"]
