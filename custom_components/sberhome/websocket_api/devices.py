"""Devices WS endpoints — list all Sber devices + detail."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..sbermap import resolve_category
from ._common import get_coordinator


def _entities_summary(entities: list) -> list[dict[str, Any]]:
    """Compact entity list for panel table — platform + unique_id + state."""
    return [
        {
            "platform": str(e.platform),
            "unique_id": e.unique_id,
            "name": e.name,
            "state": _serialize(e.state),
            "device_class": str(e.device_class) if e.device_class else None,
            "unit": e.unit_of_measurement,
        }
        for e in entities
    ]


def _serialize(value: Any) -> Any:
    """JSON-friendly serialization для VacuumActivity / HVACMode etc."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (tuple, list)):
        return [_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return str(value)


@websocket_api.websocket_command(
    {vol.Required("type"): "sberhome/get_devices"}
)
@callback
def ws_get_devices(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return ALL Sber devices + per-device enabled flag + entity count."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    enabled = coord.enabled_device_ids
    out: list[dict[str, Any]] = []
    for device_id, dto in coord.devices.items():
        category = resolve_category(dto.image_set_type)
        ents = coord.entities.get(device_id, [])
        # is_enabled: None → не настроено (legacy passthrough — все enabled).
        is_enabled = enabled is None or device_id in enabled
        out.append(
            {
                "device_id": device_id,
                "name": dto.name or device_id,
                "image_set_type": dto.image_set_type,
                "category": category,
                "model": dto.device_info.model if dto.device_info else None,
                "sw_version": dto.sw_version,
                "serial_number": dto.serial_number,
                "enabled": is_enabled,
                "entity_count": len(ents),
                "platforms": sorted({str(e.platform) for e in ents}),
            }
        )

    connection.send_result(
        msg["id"],
        {
            "devices": out,
            "configured": enabled is not None,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/device_detail",
        vol.Required("device_id"): str,
    }
)
@callback
def ws_device_detail(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return full DTO + entities + raw reported/desired state for one device."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    device_id = msg["device_id"]
    dto = coord.devices.get(device_id)
    if dto is None:
        connection.send_error(msg["id"], "not_found", f"Device {device_id} not found")
        return

    connection.send_result(
        msg["id"],
        {
            "device_id": device_id,
            "name": dto.name,
            "image_set_type": dto.image_set_type,
            "category": resolve_category(dto.image_set_type),
            "model": dto.device_info.model if dto.device_info else None,
            "sw_version": dto.sw_version,
            "serial_number": dto.serial_number,
            "reported_state": [
                {
                    "key": av.key,
                    "type": str(av.type) if av.type else None,
                    "bool_value": av.bool_value,
                    "integer_value": av.integer_value,
                    "float_value": av.float_value,
                    "string_value": av.string_value,
                    "enum_value": av.enum_value,
                }
                for av in dto.reported_state
            ],
            "desired_state": [
                {
                    "key": av.key,
                    "type": str(av.type) if av.type else None,
                    "bool_value": av.bool_value,
                    "integer_value": av.integer_value,
                    "float_value": av.float_value,
                    "string_value": av.string_value,
                    "enum_value": av.enum_value,
                }
                for av in dto.desired_state
            ],
            "ha_entities": _entities_summary(coord.entities.get(device_id, [])),
        },
    )
