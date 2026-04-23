"""Schema-validation WebSocket endpoints (DevTools #5)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/validation_issues"})
@callback
def ws_validation_issues(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return ``{recent, by_device}`` snapshot of inbound-payload issues."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(msg["id"], coord.validation_collector.snapshot())


@websocket_api.websocket_command({vol.Required("type"): "sberhome/clear_validation_issues"})
@callback
def ws_clear_validation_issues(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Drop all stored validation issues."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    coord.validation_collector.clear()
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command({vol.Required("type"): "sberhome/subscribe_validation_issues"})
@callback
def ws_subscribe_validation_issues(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Stream validation bursts to the subscriber.

    Sends the initial snapshot, then one event per snapshot that
    produced issues.  Clean snapshots (no issues) do NOT trigger an
    event — the per-device map is still updated but the UI learns
    about it on next re-fetch.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    connection.send_result(msg["id"])
    connection.send_message(
        websocket_api.event_message(msg["id"], {"snapshot": coord.validation_collector.snapshot()})
    )

    @callback
    def forward(issues: list[Any]) -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"issues": [i.as_dict() for i in issues]})
        )

    unsub = coord.validation_collector.subscribe(forward)
    connection.subscriptions[msg["id"]] = unsub
