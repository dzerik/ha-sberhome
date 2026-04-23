"""Diagnostic-advisor WebSocket command (DevTools #2).

Single request/response command — ``diagnose_device`` — that returns
a full per-device health report.  No subscribe channel: diagnostics
are user-initiated ("why isn't X working?"), there's no background
stream to push.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..diagnose import diagnose_device
from ._common import get_coordinator


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/diagnose_device",
        vol.Required("device_id"): str,
    }
)
@callback
def ws_diagnose_device(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return a full diagnostic report for ``device_id``."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    report = diagnose_device(coord, msg["device_id"])
    connection.send_result(msg["id"], {"report": report.as_dict()})
