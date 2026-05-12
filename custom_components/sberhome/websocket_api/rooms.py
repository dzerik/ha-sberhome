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
        device_filter = lambda did: cache.device_home_id(did) == requested_home_id  # noqa: E731
    else:
        home = cache.get_home()
        rooms = cache.get_rooms()
        device_filter = lambda _did: True  # noqa: E731

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


_HOME_PROBE_ENDPOINTS: tuple[str, ...] = (
    "/device_groups/tree",
    # Salute-app использует именно этот endpoint для получения всех HOME-узлов:
    # GET /gateway/v1/device_groups?group_type=HOME&pagination.offset=0&pagination.limit=N
    "/device_groups?group_type=HOME&pagination.offset=0&pagination.limit=100",
    "/device_groups?group_type=ROOM&pagination.offset=0&pagination.limit=100",
    "/device_groups?group_type=GROUP&pagination.offset=0&pagination.limit=100",
)


@websocket_api.websocket_command({vol.Required("type"): "sberhome/debug/raw_tree"})
@websocket_api.async_response
async def ws_debug_raw_tree(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Diagnostic: пробует несколько candidate-endpoints Sber API и
    возвращает для каждого количество HOME-узлов + sample raw payload.

    Используется для разбора multi-home: исходный `/device_groups/tree`
    отдаёт только дефолтный дом. Возможно есть другой endpoint, который
    возвращает все HOME-узлы юзера — проверяем кандидатов.

    UI его не зовёт в нормальной работе — только из DevTools при отладке.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    transport = coord.client.devices._transport  # type: ignore[attr-defined]
    results: list[dict[str, Any]] = []
    for url in _HOME_PROBE_ENDPOINTS:
        try:
            resp = await transport.get(url)
            payload = resp.json()
            home_count = _count_homes_in_raw(payload)
            home_names = _list_home_names(payload)
            top_level_keys = (
                sorted(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            )
            # Сохраняем payload только если он мал (плоский список)
            # — full tree слишком большой и не нужен в diagnostic-сводке.
            payload_size = len(str(payload))
            results.append(
                {
                    "url": url,
                    "status": "ok",
                    "home_count": home_count,
                    "home_names": home_names,
                    "top_level_keys": top_level_keys,
                    "payload_size_bytes": payload_size,
                    "raw": payload if payload_size < 50000 else None,
                }
            )
        except Exception as err:  # noqa: BLE001
            results.append(
                {
                    "url": url,
                    "status": "error",
                    "error": str(err)[:200],
                }
            )

    connection.send_result(msg["id"], {"results": results})


def _list_home_names(payload: Any) -> list[str]:
    """Рекурсивно собрать имена всех HOME-узлов в payload."""
    out: list[str] = []
    _walk_collect_homes(payload, out)
    return out


def _walk_collect_homes(payload: Any, out: list[str]) -> None:
    if isinstance(payload, dict):
        if isinstance(payload.get("result"), (dict, list)):
            _walk_collect_homes(payload["result"], out)
        group = payload.get("group") or payload.get("union")
        if isinstance(group, dict) and group.get("group_type") == "HOME":
            name = group.get("name") or group.get("id") or "<unnamed>"
            out.append(str(name))
        # Сама группа может быть HOME (для плоского списка).
        if payload.get("group_type") == "HOME":
            name = payload.get("name") or payload.get("id") or "<unnamed>"
            out.append(str(name))
        for child in payload.get("children") or []:
            _walk_collect_homes(child, out)
    elif isinstance(payload, list):
        for item in payload:
            _walk_collect_homes(item, out)


def _count_homes_in_raw(payload: Any) -> int:
    """Рекурсивный обход raw payload — счёт узлов с group_type=HOME."""
    if isinstance(payload, dict):
        result = 0
        if isinstance(payload.get("result"), (dict, list)):
            result += _count_homes_in_raw(payload["result"])
        group = payload.get("group") or payload.get("union")
        if isinstance(group, dict) and group.get("group_type") == "HOME":
            result += 1
        for child in payload.get("children") or []:
            result += _count_homes_in_raw(child)
        return result
    if isinstance(payload, list):
        return sum(_count_homes_in_raw(p) for p in payload)
    return 0


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
