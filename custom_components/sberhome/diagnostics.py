"""Diagnostics support for SberHome — DTO-driven + auth/WS state (P3 #32)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .coordinator import SberHomeConfigEntry

TO_REDACT = {
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "companion_tokens",
    "X-AUTH-jwt",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Содержит:
    - entry.data / entry.options (с redaction токенов).
    - devices summary (name, type, model, state keys, ha entities).
    - auth state (companion/sberid expiry) — для debug reauth issues.
    - coordinator stats (polling count, error count, WS connection, last TS).
    """
    coordinator = entry.runtime_data

    devices_summary: dict[str, Any] = {}
    auth_state: dict[str, Any] = {}
    coord_stats: dict[str, Any] = {}

    if coordinator is not None:
        if coordinator.devices:
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
                            "platform": str(ent.platform),
                            "unique_id": ent.unique_id,
                            "state_attribute_key": ent.state_attribute_key,
                        }
                        for ent in coordinator.entities.get(device_id, [])
                    ],
                }

        auth_mgr = coordinator.auth_manager
        auth_state = {
            "has_companion": auth_mgr.has_companion,
            "has_sberid_refresh": auth_mgr.has_sberid_refresh,
            "companion_expires_at": auth_mgr.companion_expires_at,
            "sberid_expires_at": auth_mgr.sberid_expires_at,
        }

        coord_stats = {
            "last_polling_at": coordinator.last_polling_at,
            "polling_count": coordinator.polling_count,
            "error_count": coordinator.error_count,
            "last_update_success": coordinator.last_update_success,
            "update_interval_seconds": (
                coordinator.update_interval.total_seconds() if coordinator.update_interval else None
            ),
            "ws_connected": coordinator.ws_connected,
            "last_ws_message_at": coordinator.last_ws_message_at,
            "ws_message_count": coordinator.ws_message_count,
        }

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "minor_version": entry.minor_version,
            "source": entry.source,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "auth": auth_state,
        "coordinator": coord_stats,
        "devices_count": len(devices_summary),
        "devices": devices_summary,
    }
