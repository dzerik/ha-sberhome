"""Device picker: opt-in enabled device set management (PR #12)."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from ..sbermap import resolve_category
from ._common import find_ha_device, get_coordinator


def _unsupported_device_ids(coord, device_ids) -> list[str]:
    """Return device_ids из списка, которые не имеют Sber-категории.

    Устройства с unknown category не создают ни одной HA entity (см.
    `map_device_to_entities` → empty list), поэтому их enable — шум без
    эффекта. Блокируем, чтобы пользователь не ловил "0 entities" сюрприз.
    """
    bad: list[str] = []
    for dev_id in device_ids:
        dto = coord.devices.get(dev_id)
        if dto is None:
            continue
        if resolve_category(dto.image_set_type) is None:
            bad.append(dev_id)
    return bad


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/set_enabled",
        vol.Required("device_ids"): [str],
    }
)
@websocket_api.async_response
async def ws_set_enabled(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the full enabled-device list (replace previous)."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    bad = _unsupported_device_ids(coord, msg["device_ids"])
    if bad:
        connection.send_error(
            msg["id"],
            "unsupported_category",
            f"Unsupported device category, cannot enable: {', '.join(bad)}",
        )
        return
    await coord.async_set_enabled_device_ids(msg["device_ids"])
    connection.send_result(
        msg["id"],
        {"success": True, "enabled_count": len(msg["device_ids"])},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/toggle_device",
        vol.Required("device_id"): str,
        vol.Required("enabled"): bool,
    }
)
@websocket_api.async_response
async def ws_toggle_device(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Toggle a single device on/off в enabled list."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    if msg["enabled"] and _unsupported_device_ids(coord, [msg["device_id"]]):
        connection.send_error(
            msg["id"],
            "unsupported_category",
            "Unsupported device category — cannot connect to Home Assistant",
        )
        return
    current = coord.enabled_device_ids
    if current is None:
        # Legacy mode — на первом toggle инициализируем set всеми known device_ids
        # (backward-compat — пока что все были «enabled»).
        current = set(coord.devices.keys())
    new_set = set(current)
    if msg["enabled"]:
        new_set.add(msg["device_id"])
    else:
        new_set.discard(msg["device_id"])
    await coord.async_set_enabled_device_ids(sorted(new_set))
    connection.send_result(
        msg["id"],
        {"success": True, "enabled": msg["enabled"], "total_enabled": len(new_set)},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/set_device_area",
        vol.Required("device_id"): str,
        vol.Required("area_id"): vol.Any(str, None),
    }
)
@websocket_api.async_response
async def ws_set_device_area(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Assign HA area (or remove) to device by Sber device_id.

    Находит HA device в device_registry по identifier (перебираем
    serial_number → dto.id → sber_device_id — логика идентична
    entity.SberHomeEntity.device_info) и обновляет area_id.
    Если area_id=None — убирает привязку к комнате.
    Если device не в HA (отключён) — возвращает error.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    ha_device = find_ha_device(hass, coord, msg["device_id"])
    if ha_device is None:
        connection.send_error(
            msg["id"],
            "device_not_in_ha",
            "Device not registered in HA (подключи сначала)",
        )
        return
    device_registry = dr.async_get(hass)
    device_registry.async_update_device(ha_device.id, area_id=msg["area_id"])
    connection.send_result(
        msg["id"],
        {"success": True, "ha_device_id": ha_device.id, "area_id": msg["area_id"]},
    )
