"""WS ``sberhome/get_status``: здоровье, последняя ошибка, отключённые опросы."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.sberhome.websocket_api.status import ws_get_status


def _coord(**overrides) -> MagicMock:
    coord = MagicMock()
    coord.devices = {"d1": object()}
    coord.enabled_device_ids = {"d1"}
    coord.enabled_device_uids = ["d1"]
    coord.update_interval = timedelta(seconds=30)
    coord.last_update_success = True
    coord.ws_connected = True
    coord.consecutive_failures = 0
    coord.last_error = None
    coord.error_count = 0
    coord.registry_maintenance_failures = 0
    coord.auth_manager = SimpleNamespace(companion_expires_at=None)
    coord.disabled_background_polls = MagicMock(return_value=[])
    coord.background_poll_states = MagicMock(return_value=[])
    for key, value in overrides.items():
        setattr(coord, key, value)
    return coord


def _call(hass: HomeAssistant, coord: MagicMock) -> dict:
    connection = MagicMock()
    entry = MagicMock(entry_id="e1", title="SberHome")
    with (
        patch(
            "custom_components.sberhome.websocket_api.status.get_coordinator", return_value=coord
        ),
        patch(
            "custom_components.sberhome.websocket_api.status.get_config_entry", return_value=entry
        ),
    ):
        ws_get_status(hass, connection, {"id": 1, "type": "sberhome/get_status"})
    return connection.send_result.call_args[0][1]


async def test_healthy_status(hass: HomeAssistant) -> None:
    result = _call(hass, _coord())
    assert result["health"] == {"score": "healthy", "issues": []}
    assert result["last_error"] is None
    assert result["disabled_polls"] == []


async def test_failing_status_reports_the_error(hass: HomeAssistant) -> None:
    error = {"kind": "SberConnectionError", "message": "timeout", "at": 1.0}
    result = _call(
        hass,
        _coord(
            last_update_success=False,
            consecutive_failures=4,
            last_error=error,
            disabled_background_polls=MagicMock(return_value=["OTA"]),
        ),
    )
    assert result["health"]["score"] == "unhealthy"
    assert [i["code"] for i in result["health"]["issues"]] == [
        "update_failing",
        "background_poll_disabled",
    ]
    assert result["last_error"] == error
    assert result["consecutive_failures"] == 4
    assert result["disabled_polls"] == ["OTA"]
    assert "background_polls" in result
