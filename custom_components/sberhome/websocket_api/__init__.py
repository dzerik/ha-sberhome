"""WebSocket API package for SberHome panel (PR #12).

Provides real-time data to the frontend SPA panel via Home Assistant native
WebSocket commands. Split across domain modules:

- ``_common``  — shared `get_coordinator` / `get_config_entry` helpers.
- ``status``   — connection + polling stats, token expiry, WS connection.
- ``devices``  — list ALL Sber devices + per-device enabled flag, device detail.
- ``enabled``  — set/toggle enabled set (opt-in device picker).
- ``log``      — WS message ring buffer + subscribe.
- ``settings`` — get/update_settings, force refresh.
"""

from __future__ import annotations

import logging

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import DOMAIN
from .devices import ws_device_detail, ws_get_devices
from .enabled import ws_set_enabled, ws_toggle_device
from .log import ws_clear_message_log, ws_message_log, ws_subscribe_messages
from .rooms import ws_get_rooms
from .settings import ws_force_refresh, ws_get_settings, ws_update_settings
from .status import ws_get_status

_LOGGER = logging.getLogger(__name__)

_COMMANDS = (
    ws_get_status,
    ws_get_devices,
    ws_device_detail,
    ws_set_enabled,
    ws_toggle_device,
    ws_message_log,
    ws_clear_message_log,
    ws_subscribe_messages,
    ws_get_rooms,
    ws_get_settings,
    ws_update_settings,
    ws_force_refresh,
)


@callback
def async_setup_websocket_api(hass: HomeAssistant) -> None:
    """Idempotent registration of all SberHome panel WS commands."""
    marker = f"{DOMAIN}_ws_registered"
    if hass.data.get(marker):
        return
    hass.data[marker] = True
    for command in _COMMANDS:
        websocket_api.async_register_command(hass, command)
    _LOGGER.debug("SberHome WebSocket API registered")


__all__ = [
    "async_setup_websocket_api",
    "ws_clear_message_log",
    "ws_device_detail",
    "ws_force_refresh",
    "ws_get_devices",
    "ws_get_settings",
    "ws_get_status",
    "ws_message_log",
    "ws_set_enabled",
    "ws_subscribe_messages",
    "ws_toggle_device",
    "ws_update_settings",
]
