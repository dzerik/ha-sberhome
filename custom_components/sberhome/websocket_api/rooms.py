"""Rooms WS endpoint — room list with device counts."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_coordinator


@websocket_api.websocket_command(
    {vol.Required("type"): "sberhome/get_rooms"}
)
@callback
def ws_get_rooms(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all Sber rooms with device counts."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    cache = coord.state_cache
    home = cache.get_home()
    rooms = cache.get_rooms()

    rooms_out: list[dict[str, Any]] = []
    for room in rooms:
        device_count = sum(
            1 for did in cache.get_all_devices()
            if cache.device_room_id(did) == room.id
        )
        rooms_out.append({
            "id": room.id,
            "name": room.name,
            "device_count": device_count,
            "image_set_type": room.image_set_type,
        })

    connection.send_result(
        msg["id"],
        {
            "home": {
                "id": home.id,
                "name": home.name,
            } if home else None,
            "rooms": rooms_out,
            "total_devices": len(cache.get_all_devices()),
        },
    )
