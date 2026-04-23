"""Tests for the command-tracker WebSocket commands.

Guards the payload shape the DevTools panel reads directly
(``commands`` / ``command`` / ``snapshot`` / ``kind``).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sberhome.command_tracker import CommandTracker
from custom_components.sberhome.websocket_api.commands import (
    ws_clear_commands,
    ws_commands,
    ws_subscribe_commands,
)


def _seeded_coord() -> MagicMock:
    coord = MagicMock()
    coord.command_tracker = CommandTracker()
    coord.command_tracker.record_sent(
        "dev-1",
        [{"key": "on_off", "type": "BOOL", "bool_value": True}],
    )
    return coord


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    conn.send_message = MagicMock()
    conn.subscriptions = {}
    return conn


@pytest.fixture
def hass():
    return MagicMock()


class TestCommandsList:
    def test_returns_snapshot(self, hass, connection):
        coord = _seeded_coord()
        with patch(
            "custom_components.sberhome.websocket_api.commands.get_coordinator",
            return_value=coord,
        ):
            ws_commands(hass, connection, {"id": 1})
        payload = connection.send_result.call_args[0][1]
        assert "commands" in payload
        assert payload["commands"][0]["device_id"] == "dev-1"
        assert payload["commands"][0]["status"] == "pending"

    def test_missing_coordinator_sends_error(self, hass, connection):
        with patch(
            "custom_components.sberhome.websocket_api.commands.get_coordinator",
            return_value=None,
        ):
            ws_commands(hass, connection, {"id": 1})
        connection.send_error.assert_called_once()


class TestClearCommands:
    def test_clear_empties_tracker(self, hass, connection):
        coord = _seeded_coord()
        with patch(
            "custom_components.sberhome.websocket_api.commands.get_coordinator",
            return_value=coord,
        ):
            ws_clear_commands(hass, connection, {"id": 2})
        assert coord.command_tracker.snapshot() == []


class TestSubscribeCommands:
    def test_subscribe_sends_snapshot_then_live(self, hass, connection):
        coord = _seeded_coord()
        with patch(
            "custom_components.sberhome.websocket_api.commands.get_coordinator",
            return_value=coord,
        ):
            ws_subscribe_commands(hass, connection, {"id": 3})
            # Another command — subscriber must see it as a live event.
            coord.command_tracker.record_sent(
                "dev-2",
                [{"key": "on_off", "type": "BOOL", "bool_value": False}],
            )

        # Initial snapshot + one live event.
        assert connection.send_message.call_count >= 2
        # Subscription handle tracked for HA auto-unsub.
        assert 3 in connection.subscriptions
