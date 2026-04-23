"""Tests for the per-device diagnose WebSocket command.

Guards the payload shape the panel reads directly (``{"report": {...}}``)
and the error path (missing coordinator).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.dto.values import (
    AttributeValueDto,
    AttributeValueType,
)
from custom_components.sberhome.websocket_api.diagnose import ws_diagnose_device


def _coord_with_device(device_id: str = "dev-1") -> MagicMock:
    dto = DeviceDto(
        id=device_id,
        image_set_type="cat_light_basic",
        reported_state=[
            AttributeValueDto(key="online", type=AttributeValueType.BOOL, bool_value=True),
        ],
    )
    coord = MagicMock()
    coord.state_cache.get_device = MagicMock(return_value=dto)
    coord.state_cache.get_all_devices = MagicMock(return_value={device_id: dto})
    coord.enabled_device_ids = {device_id}
    coord.entities = {device_id: [MagicMock()]}
    coord.ws_connected = True
    coord.error_count = 0
    coord.last_ws_message_at = None
    coord.last_polling_at = None
    auth = MagicMock()
    auth.companion_expires_at = None
    auth.sberid_expires_at = None
    coord.auth_manager = auth
    return coord


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture
def hass():
    return MagicMock()


class TestDiagnoseDevice:
    def test_clean_device_returns_ok_verdict(self, hass, connection):
        with patch(
            "custom_components.sberhome.websocket_api.diagnose.get_coordinator",
            return_value=_coord_with_device(),
        ):
            ws_diagnose_device(hass, connection, {"id": 1, "device_id": "dev-1"})
        payload = connection.send_result.call_args[0][1]
        assert "report" in payload
        # UI reads these four top-level fields — renames break the panel.
        assert set(payload["report"].keys()) >= {"device_id", "verdict", "findings", "summary"}
        assert payload["report"]["verdict"] == "ok"

    def test_unknown_device_returns_broken_not_error(self, hass, connection):
        # A user typing a non-existent id is a legit diagnostic path —
        # must return the "not_in_tree" finding, not a WS error that
        # hides the diagnosis from them.
        coord = _coord_with_device()
        coord.state_cache.get_device = MagicMock(return_value=None)
        coord.state_cache.get_all_devices = MagicMock(return_value={})
        with patch(
            "custom_components.sberhome.websocket_api.diagnose.get_coordinator",
            return_value=coord,
        ):
            ws_diagnose_device(hass, connection, {"id": 2, "device_id": "nope"})
        payload = connection.send_result.call_args[0][1]
        assert payload["report"]["verdict"] == "broken"
        connection.send_error.assert_not_called()

    def test_missing_coordinator_sends_error(self, hass, connection):
        with patch(
            "custom_components.sberhome.websocket_api.diagnose.get_coordinator",
            return_value=None,
        ):
            ws_diagnose_device(hass, connection, {"id": 3, "device_id": "dev-1"})
        err = connection.send_error.call_args
        assert err[0][1] == "not_loaded"
