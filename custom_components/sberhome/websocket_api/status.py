"""Status WS endpoint — token, WS connection, polling stats, errors."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_config_entry, get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/get_status"})
@callback
def ws_get_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return SberHome integration health status."""
    coord = get_coordinator(hass)
    entry = get_config_entry(hass)
    if coord is None or entry is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    # Tokens живут в HomeAPI.AuthManager (после перехода на aiosber 2.6.0).
    # SberID хранится также в SberAPI (для config_entry.data persistence),
    # но canonical источник истины для runtime — AuthManager.
    auth = coord.auth_manager
    sberid_expires = auth.sberid_expires_at
    companion_expires = auth.companion_expires_at

    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "devices_total": len(coord.devices),
            "devices_enabled": (
                len(coord.enabled_device_ids)
                if coord.enabled_device_ids is not None
                else len(coord.devices)
            ),
            "polling": {
                "last_at": coord.last_polling_at,
                "count": coord.polling_count,
                "interval_seconds": coord.update_interval.total_seconds()
                if coord.update_interval
                else None,
                "last_success": coord.last_update_success,
            },
            "ws": {
                "connected": coord.ws_connected,
                "last_message_at": coord.last_ws_message_at,
                "message_count": coord.ws_message_count,
            },
            "tokens": {
                "sberid_expires_at": sberid_expires,
                "companion_expires_at": companion_expires,
            },
            "error_count": coord.error_count,
        },
    )
