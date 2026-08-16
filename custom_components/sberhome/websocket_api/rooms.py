"""Rooms WS endpoint — room list, rename, refresh scenarios/OTA."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ._common import get_coordinator


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/get_rooms",
        vol.Optional("home_id"): vol.Any(str, None),
    }
)
@callback
def ws_get_rooms(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return Sber rooms with device counts.

    Опциональный `home_id` фильтр — если задан, возвращаются только rooms
    указанного дома, и `total_devices` считается только по нему. Без
    параметра — поведение legacy (все rooms всех домов).
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    cache = coord.state_cache
    requested_home_id = msg.get("home_id")

    if requested_home_id is not None:
        home = cache.get_group(requested_home_id)
        rooms = cache.get_rooms(home_id=requested_home_id)

        def device_filter(did: str) -> bool:
            return cache.device_home_id(did) == requested_home_id
    else:
        home = cache.get_home()
        rooms = cache.get_rooms()

        def device_filter(_did: str) -> bool:
            return True

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

    total_devices = sum(1 for did in cache.get_all_devices() if device_filter(did))

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
            "total_devices": total_devices,
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "sberhome/get_homes"})
@callback
def ws_get_homes(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return all Sber HOME-узлы текущего юзера с метаданными.

    Для multi-home поддержки (issue #2) — UI dropdown в панели использует
    этот endpoint чтобы отрисовать switcher. `is_default` — флаг первого
    HOME (используется legacy single-home accessor'ом `get_home()`).
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    cache = coord.state_cache
    homes = cache.get_homes()
    default_id = homes[0].id if homes else None

    homes_out: list[dict[str, Any]] = []
    for home in homes:
        device_count = sum(
            1 for did in cache.get_all_devices() if cache.device_home_id(did) == home.id
        )
        room_count = sum(1 for _ in cache.get_rooms(home_id=home.id))
        homes_out.append(
            {
                "id": home.id,
                "name": home.name,
                "room_count": room_count,
                "device_count": device_count,
                "is_default": home.id == default_id,
            }
        )

    connection.send_result(msg["id"], {"homes": homes_out})


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
    except Exception as err:
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
    """Manual refresh сценариев + at_home — сбрасывает scenarios-poll disable-флаг."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        await coord.async_refresh_scenarios()
    except Exception as err:
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
    """Manual refresh OTA-upgrades — сбрасывает OTA-poll disable-флаг."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        await coord.async_refresh_ota()
    except Exception as err:
        connection.send_error(msg["id"], "refresh_failed", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "success": True,
            "device_count": len(coord.ota_upgrades),
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "sberhome/get_groups"})
@callback
def ws_get_groups(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Кастомные группы (group_type=GROUP) с счётчиком устройств + entity_id свитча.

    Панель рисует секцию «Группы»: bulk-переключатель на каждую группу
    (управляет через штатный `switch.…` по `entity_id`).
    """
    from homeassistant.helpers import entity_registry as er

    from ..aiosber.dto.union import UnionType
    from ..const import DOMAIN

    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    cache = coord.state_cache
    ent_reg = er.async_get(hass)
    groups_out: list[dict[str, Any]] = []
    for group_id, group in cache.get_all_groups().items():
        if group.group_type is not UnionType.GROUP:
            continue
        devices = cache.get_group_devices(group_id)
        if not devices:
            continue
        groups_out.append(
            {
                "id": group_id,
                "name": group.name,
                "device_count": len(devices),
                "entity_id": ent_reg.async_get_entity_id(
                    "switch", DOMAIN, f"sber_group_{group_id}"
                ),
                "image_set_type": group.image_set_type,
            }
        )

    connection.send_result(msg["id"], {"groups": groups_out})
