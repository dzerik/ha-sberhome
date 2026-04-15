"""Diagnostics support for SberHome."""

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

    devices_summary = {}
    if coordinator and coordinator.data:
        for device_id, device in coordinator.data.items():
            devices_summary[device_id] = {
                "name": device.get("name", {}).get("name", "unknown"),
                "type": device.get("image_set_type", "unknown"),
                "model": device.get("device_info", {}).get("model", "unknown"),
                "sw_version": device.get("sw_version", "unknown"),
                "desired_state_keys": [
                    s["key"] for s in device.get("desired_state", [])
                ],
                "reported_state_keys": [
                    s["key"] for s in device.get("reported_state", [])
                ],
                "attribute_keys": [
                    a["key"] for a in device.get("attributes", [])
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
