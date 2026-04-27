"""Rooms WS endpoint — room list, rename, refresh scenarios/OTA."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/get_rooms"})
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
            1 for did in cache.get_all_devices() if cache.device_room_id(did) == room.id
        )
        rooms_out.append(
            {
                "id": room.id,
                "name": room.name,
                "device_count": device_count,
                "image_set_type": room.image_set_type,
            }
        )

    connection.send_result(
        msg["id"],
        {
            "home": {
                "id": home.id,
                "name": home.name,
            }
            if home
            else None,
            "rooms": rooms_out,
            "total_devices": len(cache.get_all_devices()),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/rename_room",
        vol.Required("room_id"): str,
        vol.Required("name"): vol.All(str, vol.Length(min=1, max=128)),
    }
)
@websocket_api.async_response
async def ws_rename_room(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Rename a Sber room (group) via GroupAPI.rename → trigger refresh."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        await coord.client.groups.rename(msg["room_id"], msg["name"])
    except Exception as err:  # noqa: BLE001 — surface to UI
        connection.send_error(msg["id"], "rename_failed", str(err))
        return
    # Refresh tree чтобы UI увидел новое имя сразу.
    await coord.async_request_refresh()
    connection.send_result(
        msg["id"],
        {"success": True, "room_id": msg["room_id"], "name": msg["name"]},
    )


@websocket_api.websocket_command({vol.Required("type"): "sberhome/refresh_scenarios"})
@websocket_api.async_response
async def ws_refresh_scenarios(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Manual refresh сценариев + at_home — сбрасывает _scenarios_disabled."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        await coord.async_refresh_scenarios()
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "refresh_failed", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "success": True,
            "scenario_count": len(coord.scenarios),
            "at_home": coord.at_home,
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "sberhome/refresh_ota"})
@websocket_api.async_response
async def ws_refresh_ota(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Manual refresh OTA-upgrades — сбрасывает _ota_disabled."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        await coord.async_refresh_ota()
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "refresh_failed", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "success": True,
            "device_count": len(coord.ota_upgrades),
        },
    )
