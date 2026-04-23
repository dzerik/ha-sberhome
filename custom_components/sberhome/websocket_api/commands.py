"""Command-tracker WebSocket endpoints (DevTools #4).

Frontend counterpart to
:mod:`custom_components.sberhome.command_tracker`.  Returns snapshots
and streams live command lifecycle events so the DevTools tab can
surface silent rejections the moment the timeout hits.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/commands"})
@callback
def ws_commands(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the ring-buffer snapshot of outbound commands."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(msg["id"], {"commands": coord.command_tracker.snapshot()})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/clear_commands"})
@callback
def ws_clear_commands(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Drop all active and closed command records."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    coord.command_tracker.clear()
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/subscribe_commands"})
@callback
def ws_subscribe_commands(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stream command lifecycle events to the subscriber.

    Sends initial ``{"snapshot": [...]}``, then ``{"kind": ..., "command": ...}``
    for every ``command_sent`` / ``command_updated`` / ``command_closed``
    event.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    connection.send_result(msg["id"])
    connection.send_message(
        websocket_api.event_message(msg["id"], {"snapshot": coord.command_tracker.snapshot()})
    )

    @callback
    def forward(kind: str, cmd: Any) -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"kind": kind, "command": cmd.as_dict()})
        )

    unsub = coord.command_tracker.subscribe(forward)
    connection.subscriptions[msg["id"]] = unsub
