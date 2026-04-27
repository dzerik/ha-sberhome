"""Tests для новых WS endpoints — rename_room, refresh_scenarios, refresh_ota."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sberhome.websocket_api.rooms import (
    ws_refresh_ota,
    ws_refresh_scenarios,
    ws_rename_room,
)


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture
def hass():
    return MagicMock()


def _coord() -> MagicMock:
    coord = MagicMock()
    coord.client = MagicMock()
    coord.client.groups = MagicMock()
    coord.client.groups.rename = AsyncMock()
    coord.async_request_refresh = AsyncMock()
    coord.async_refresh_scenarios = AsyncMock()
    coord.async_refresh_ota = AsyncMock()
    coord.scenarios = []
    coord.at_home = None
    coord.ota_upgrades = {}
    return coord


# ---------------------------------------------------------------------------
# rename_room
# ---------------------------------------------------------------------------


class TestRenameRoom:
    @pytest.mark.asyncio
    async def test_rename_calls_group_api_and_refreshes(self, hass, connection):
        coord = _coord()
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            await ws_rename_room.__wrapped__(
                hass,
                connection,
                {"id": 1, "room_id": "g-1", "name": "Гостиная"},
            )
        coord.client.groups.rename.assert_awaited_once_with("g-1", "Гостиная")
        coord.async_request_refresh.assert_awaited_once()
        connection.send_error.assert_not_called()

    @pytest.mark.asyncio
    async def test_rename_returns_error_on_api_failure(self, hass, connection):
        coord = _coord()
        coord.client.groups.rename.side_effect = RuntimeError("403")
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            await ws_rename_room.__wrapped__(
                hass, connection, {"id": 2, "room_id": "g-1", "name": "X"}
            )
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "rename_failed"
        coord.async_request_refresh.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rename_when_no_coordinator(self, hass, connection):
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=None,
        ):
            await ws_rename_room.__wrapped__(
                hass, connection, {"id": 3, "room_id": "g-1", "name": "X"}
            )
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "not_loaded"


# ---------------------------------------------------------------------------
# refresh_scenarios
# ---------------------------------------------------------------------------


class TestRefreshScenarios:
    @pytest.mark.asyncio
    async def test_calls_coordinator_and_returns_summary(self, hass, connection):
        coord = _coord()
        coord.scenarios = [MagicMock(), MagicMock(), MagicMock()]
        coord.at_home = True
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            await ws_refresh_scenarios.__wrapped__(hass, connection, {"id": 4})
        coord.async_refresh_scenarios.assert_awaited_once()
        result = connection.send_result.call_args[0][1]
        assert result == {"success": True, "scenario_count": 3, "at_home": True}

    @pytest.mark.asyncio
    async def test_surfaces_refresh_error(self, hass, connection):
        coord = _coord()
        coord.async_refresh_scenarios.side_effect = RuntimeError("token expired")
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            await ws_refresh_scenarios.__wrapped__(hass, connection, {"id": 5})
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "refresh_failed"


# ---------------------------------------------------------------------------
# refresh_ota
# ---------------------------------------------------------------------------


class TestRefreshOta:
    @pytest.mark.asyncio
    async def test_calls_coordinator_and_returns_count(self, hass, connection):
        coord = _coord()
        coord.ota_upgrades = {"d1": {"available_version": "2.0"}}
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            await ws_refresh_ota.__wrapped__(hass, connection, {"id": 6})
        coord.async_refresh_ota.assert_awaited_once()
        result = connection.send_result.call_args[0][1]
        assert result == {"success": True, "device_count": 1}
