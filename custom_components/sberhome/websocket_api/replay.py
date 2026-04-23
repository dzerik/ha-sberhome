"""Replay / inject WebSocket commands (DevTools #3).

Forwards a synthetic WebSocket payload into the coordinator dispatcher
without touching the broker.  The same pipeline that handles live Sber
WS traffic — ``_on_ws_device_state`` / ``_on_ws_devman_event`` /
``_on_ws_group_state`` — sees injected messages indistinguishably from
real ones (except for the ``direction="replay"`` marker in the WS log).

Two commands:
    * ``inject_ws_message`` — arbitrary ``{"payload": {...}}``.
    * ``replay_ws_message`` — convenience alias for re-sending an entry
      from the message log (log rows carry ``{payload, topic, ...}``
      already; this is a thin alias so the UI stays declarative).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ._common import get_coordinator


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/inject_ws_message",
        vol.Required("payload"): dict,
        vol.Optional("mark_replay", default=True): bool,
    }
)
@websocket_api.async_response
async def ws_inject_ws_message(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Inject a synthetic WS message into the coordinator dispatcher."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        result = await coord.async_inject_ws_message(msg["payload"], mark_replay=msg["mark_replay"])
    except (ValueError, TypeError, RuntimeError) as e:
        # Explicit error channel — otherwise the UI sees a generic
        # timeout and the user has no idea why the inject silently failed.
        connection.send_error(msg["id"], "inject_failed", str(e))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/replay_ws_message",
        vol.Required("payload"): dict,
    }
)
@websocket_api.async_response
async def ws_replay_ws_message(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Re-send a previously-captured WS payload (always marked as replay)."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        result = await coord.async_inject_ws_message(msg["payload"], mark_replay=True)
    except (ValueError, TypeError, RuntimeError) as e:
        connection.send_error(msg["id"], "replay_failed", str(e))
        return
    connection.send_result(msg["id"], result)
