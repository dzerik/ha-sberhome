"""WS message ring buffer endpoints."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/message_log"})
@callback
def ws_message_log(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return ring buffer last 100 WS messages."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(msg["id"], {"messages": list(coord._ws_log)})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/clear_message_log"})
@callback
def ws_clear_message_log(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Clear the WS message ring buffer."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    coord._ws_log.clear()
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/subscribe_messages"})
@callback
def ws_subscribe_messages(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Subscribe to real-time WS message log updates + initial snapshot."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    connection.send_result(msg["id"])
    connection.send_message(
        websocket_api.event_message(msg["id"], {"snapshot": list(coord._ws_log)})
    )

    @callback
    def forward(message_data: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], {"message": message_data}))

    coord._ws_log_subscribers.append(forward)

    @callback
    def _unsub() -> None:
        import contextlib

        with contextlib.suppress(ValueError):
            coord._ws_log_subscribers.remove(forward)

    connection.subscriptions[msg["id"]] = _unsub
