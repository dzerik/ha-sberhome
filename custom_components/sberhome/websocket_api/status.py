"""Status WS endpoint — token, WS connection, polling stats, errors."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_config_entry, get_coordinator


@websocket_api.websocket_command(
    {vol.Required("type"): "sberhome/get_status"}
)
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

    sber = coord.sber_api
    sberid_expires = (
        sber._sberid.expires_at if sber._sberid is not None else None
    )
    companion_expires = (
        sber._companion.expires_at if sber._companion is not None else None
    )

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
                "connected": (
                    coord._ws_client.is_connected
                    if coord._ws_client is not None
                    else False
                ),
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
