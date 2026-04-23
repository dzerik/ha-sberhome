"""State-diff WebSocket endpoints (DevTools #1).

Frontend counterpart to
:mod:`custom_components.sberhome.state_diff`.  Returns JSON-serializable
snapshots and fans out live updates through a subscription channel so
the DevTools tab can render deltas in real time.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/state_diffs"})
@callback
def ws_state_diffs(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the ring-buffer snapshot of recent state diffs."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(msg["id"], {"diffs": coord.diff_collector.snapshot()})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/clear_state_diffs"})
@callback
def ws_clear_state_diffs(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Drop all recorded diffs and the per-device baseline."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    coord.diff_collector.clear()
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/subscribe_state_diffs"})
@callback
def ws_subscribe_state_diffs(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stream state diffs to the subscriber.

    Sends an initial ``{"snapshot": [...]}`` event, then ``{"diff": {...}}``
    for each subsequent non-empty diff.  Identical snapshots (nothing
    changed) are silently dropped by the collector — subscribers
    receive only meaningful events.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    connection.send_result(msg["id"])
    connection.send_message(
        websocket_api.event_message(msg["id"], {"snapshot": coord.diff_collector.snapshot()})
    )

    @callback
    def forward(diff: Any) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], {"diff": diff.as_dict()}))

    unsub = coord.diff_collector.subscribe(forward)
    connection.subscriptions[msg["id"]] = unsub
