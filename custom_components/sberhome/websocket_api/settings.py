"""Settings WS endpoints — get/update + force refresh."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from ._common import get_config_entry, get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/get_settings"})
@callback
def ws_get_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current settings (scan_interval, others)."""
    entry = get_config_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(
        msg["id"],
        {
            "scan_interval": entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/update_settings",
        vol.Optional("scan_interval"): vol.All(int, vol.Range(min=10, max=3600)),
    }
)
@websocket_api.async_response
async def ws_update_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update settings + persist в config_entry.options."""
    entry = get_config_entry(hass)
    coord = get_coordinator(hass)
    if entry is None or coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    new_options = dict(entry.options)
    if "scan_interval" in msg:
        new_options[CONF_SCAN_INTERVAL] = msg["scan_interval"]
        coord.update_interval = timedelta(seconds=msg["scan_interval"])
        coord._user_update_interval = timedelta(seconds=msg["scan_interval"])
    hass.config_entries.async_update_entry(entry, options=new_options)
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/force_refresh"})
@websocket_api.async_response
async def ws_force_refresh(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Force coordinator refresh (immediate REST poll)."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    await coord.async_request_refresh()
    connection.send_result(msg["id"], {"success": True})
