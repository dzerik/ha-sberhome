"""WebSocket API package for SberHome panel (PR #12).

Provides real-time data to the frontend SPA panel via Home Assistant native
WebSocket commands. Split across domain modules:

- ``_common``  — shared `get_coordinator` / `get_config_entry` helpers.
- ``status``   — connection + polling stats, token expiry, WS connection.
- ``devices``  — list ALL Sber devices + per-device enabled flag, device detail.
- ``enabled``  — set/toggle enabled set (opt-in device picker).
- ``log``      — WS message ring buffer + subscribe.
- ``settings`` — get/update_settings, force refresh.
- ``state_diffs`` — per-device reported_state deltas (DevTools #1).
- ``diagnose``   — per-device diagnostic advisor (DevTools #2).
- ``replay``     — replay / inject WS messages (DevTools #3).
- ``commands``   — outbound command confirmation tracker (DevTools #4).
- ``validation`` — inbound payload schema validator (DevTools #5).
"""

from __future__ import annotations

import logging

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import DOMAIN
from .commands import ws_clear_commands, ws_commands, ws_subscribe_commands
from .devices import ws_device_detail, ws_get_devices, ws_refetch_device
from .diagnose import ws_diagnose_device
from .enabled import ws_set_device_area, ws_set_enabled, ws_toggle_device
from .log import ws_clear_message_log, ws_message_log, ws_subscribe_messages
from .replay import ws_inject_ws_message, ws_replay_ws_message
from .rooms import ws_get_rooms, ws_refresh_ota, ws_refresh_scenarios, ws_rename_room
from .settings import ws_force_refresh, ws_get_settings, ws_update_settings
from .state_diffs import (
    ws_clear_state_diffs,
    ws_state_diffs,
    ws_subscribe_state_diffs,
)
from .status import ws_get_status
from .validation import (
    ws_clear_validation_issues,
    ws_subscribe_validation_issues,
    ws_validation_issues,
)

_LOGGER = logging.getLogger(__name__)

_COMMANDS = (
    ws_get_status,
    ws_get_devices,
    ws_device_detail,
    ws_refetch_device,
    ws_set_device_area,
    ws_set_enabled,
    ws_toggle_device,
    ws_message_log,
    ws_clear_message_log,
    ws_subscribe_messages,
    ws_get_rooms,
    ws_rename_room,
    ws_refresh_scenarios,
    ws_refresh_ota,
    ws_get_settings,
    ws_update_settings,
    ws_force_refresh,
    # DevTools #1 — state diffs (v3.10.0)
    ws_state_diffs,
    ws_clear_state_diffs,
    ws_subscribe_state_diffs,
    # DevTools #2 — per-device diagnose (v3.11.0)
    ws_diagnose_device,
    # DevTools #3 — replay / inject WS (v3.12.0)
    ws_inject_ws_message,
    ws_replay_ws_message,
    # DevTools #4 — command confirmation tracker (v3.13.0)
    ws_commands,
    ws_clear_commands,
    ws_subscribe_commands,
    # DevTools #5 — inbound schema validator (v3.14.0)
    ws_validation_issues,
    ws_clear_validation_issues,
    ws_subscribe_validation_issues,
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
    "ws_clear_commands",
    "ws_clear_message_log",
    "ws_clear_state_diffs",
    "ws_clear_validation_issues",
    "ws_commands",
    "ws_device_detail",
    "ws_diagnose_device",
    "ws_force_refresh",
    "ws_get_devices",
    "ws_get_settings",
    "ws_get_status",
    "ws_inject_ws_message",
    "ws_message_log",
    "ws_refetch_device",
    "ws_replay_ws_message",
    "ws_set_device_area",
    "ws_set_enabled",
    "ws_state_diffs",
    "ws_subscribe_commands",
    "ws_subscribe_messages",
    "ws_subscribe_state_diffs",
    "ws_subscribe_validation_issues",
    "ws_toggle_device",
    "ws_update_settings",
    "ws_validation_issues",
]
