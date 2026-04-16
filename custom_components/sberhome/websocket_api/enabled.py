"""Device picker: opt-in enabled device set management (PR #12)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ._common import get_coordinator


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/set_enabled",
        vol.Required("device_ids"): [str],
    }
)
@websocket_api.async_response
async def ws_set_enabled(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the full enabled-device list (replace previous)."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    await coord.async_set_enabled_device_ids(msg["device_ids"])
    connection.send_result(
        msg["id"],
        {"success": True, "enabled_count": len(msg["device_ids"])},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/toggle_device",
        vol.Required("device_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response
async def ws_toggle_device(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Toggle a single device on/off в enabled list."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    current = coord.enabled_device_ids
    if current is None:
        # Legacy mode — на первом toggle инициализируем set всеми known device_ids
        # (backward-compat — пока что все были «enabled»).
        current = set(coord.devices.keys())
    new_set = set(current)
    if msg["enabled"]:
        new_set.add(msg["device_id"])
    else:
        new_set.discard(msg["device_id"])
    await coord.async_set_enabled_device_ids(sorted(new_set))
    connection.send_result(
        msg["id"],
        {"success": True, "enabled": msg["enabled"], "total_enabled": len(new_set)},
    )
