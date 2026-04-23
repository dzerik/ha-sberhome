"""Tests for the state-diff WebSocket commands.

Guards the shape of WS payloads the DevTools panel reads directly
(``diffs`` / ``diff`` / ``snapshot``) and the error paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sberhome.state_diff import DiffCollector
from custom_components.sberhome.websocket_api.state_diffs import (
    ws_clear_state_diffs,
    ws_state_diffs,
    ws_subscribe_state_diffs,
)


def _seeded_coordinator() -> MagicMock:
    coord = MagicMock()
    coord.diff_collector = DiffCollector()
    coord.diff_collector.update(
        "dev-1",
        [{"key": "on_off", "type": "BOOL", "bool_value": True}],
    )
    coord.diff_collector.update(
        "dev-1",
        [{"key": "on_off", "type": "BOOL", "bool_value": False}],
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


class TestListStateDiffs:
    def test_returns_snapshot(self, hass, connection):
        coord = _seeded_coordinator()
        with patch(
            "custom_components.sberhome.websocket_api.state_diffs.get_coordinator",
            return_value=coord,
        ):
            ws_state_diffs(hass, connection, {"id": 1})
        payload = connection.send_result.call_args[0][1]
        # Field names match the coordinator contract — UI reads them directly.
        assert "diffs" in payload
        assert payload["diffs"][0]["device_id"] == "dev-1"
        assert payload["diffs"][0]["changed"]["on_off"]["after"]["bool_value"] is False

    def test_missing_coordinator_sends_error(self, hass, connection):
        with patch(
            "custom_components.sberhome.websocket_api.state_diffs.get_coordinator",
            return_value=None,
        ):
            ws_state_diffs(hass, connection, {"id": 1})
        # Explicit error code lets the UI show "integration not loaded"
        # instead of a generic timeout.
        err = connection.send_error.call_args
        assert err[0][1] == "not_loaded"


class TestClearStateDiffs:
    def test_clear_empties_collector(self, hass, connection):
        coord = _seeded_coordinator()
        with patch(
            "custom_components.sberhome.websocket_api.state_diffs.get_coordinator",
            return_value=coord,
        ):
            ws_clear_state_diffs(hass, connection, {"id": 2})
        assert coord.diff_collector.snapshot() == []


class TestSubscribeStateDiffs:
    def test_subscribe_sends_snapshot_then_live_updates(self, hass, connection):
        coord = _seeded_coordinator()
        with patch(
            "custom_components.sberhome.websocket_api.state_diffs.get_coordinator",
            return_value=coord,
        ):
            ws_subscribe_state_diffs(hass, connection, {"id": 3})
            # Another real change after subscribe — subscriber must see it.
            coord.diff_collector.update(
                "dev-1",
                [{"key": "on_off", "type": "BOOL", "bool_value": True}],
            )

        # One initial snapshot + one live diff.
        assert connection.send_message.call_count >= 2
        # Subscription handle tracked for HA auto-unsub on disconnect.
        assert 3 in connection.subscriptions
