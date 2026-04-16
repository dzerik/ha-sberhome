"""Diagnostics support for SberHome — DTO-driven (PR #8)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .coordinator import SberHomeConfigEntry

TO_REDACT = {"access_token", "refresh_token", "id_token", "token", "X-AUTH-jwt"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data

    devices_summary: dict[str, Any] = {}
    if coordinator and coordinator.devices:
        for device_id, dto in coordinator.devices.items():
            devices_summary[device_id] = {
                "name": dto.name,
                "type": dto.image_set_type,
                "model": dto.device_info.model if dto.device_info else None,
                "sw_version": dto.sw_version,
                "desired_state_keys": [av.key for av in dto.desired_state],
                "reported_state_keys": [av.key for av in dto.reported_state],
                "ha_entities": [
                    {
                        "platform": ent.platform,
                        "unique_id": ent.unique_id,
                        "state_attribute_key": ent.state_attribute_key,
                    }
                    for ent in coordinator.entities.get(device_id, [])
                ],
            }

    return {
        "entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "devices_count": len(devices_summary),
        "devices": devices_summary,
    }
