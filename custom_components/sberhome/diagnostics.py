"""Diagnostics support for SberHome — DTO-driven + auth/WS state (P3 #32)."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .coordinator import SberHomeConfigEntry

_LOGGER = logging.getLogger(__name__)

TO_REDACT = {
    "access_token",
    "refresh_token",
    "id_token",
    "token",
    "companion_tokens",
    "X-AUTH-jwt",
    # SMS login (CSAFront) stores its tokens under names of its own.
    "csafront_access_token",
    "csafront_refresh_token",
    "smart_home_token",
    "client_uuid",
    "phone",
}
"""Keys whose values never leave the host in a diagnostics download."""

_PHONE_RE = re.compile(r"\+?\d[\d\s()-]{8,}\d")
"""A phone number as it appears in an SMS-login entry title."""


DEVTOOLS_REDACT = TO_REDACT | {"mac_address", "ip_address", "ssid", "bssid", "password"}
"""Ключи, скрываемые в данных DevTools: адреса в локальной сети вдобавок к токенам."""

DEVTOOLS_MESSAGES = 100
"""Сколько последних WS-сообщений попадает в файл."""

DEVTOOLS_RECORDS = 50
"""Сколько последних изменений, команд и замечаний проверки попадает в файл."""

STRING_MAX_CHARS = 2000
"""Длинные строки обрезаются, чтобы файл оставался пригодным для вложения."""


def _truncate_strings(value: Any) -> Any:
    """Обрезать длинные строки на любой глубине вложенности."""
    if isinstance(value, str) and len(value) > STRING_MAX_CHARS:
        return value[:STRING_MAX_CHARS] + "…[truncated]"
    if isinstance(value, dict):
        return {k: _truncate_strings(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_truncate_strings(v) for v in value]
    return value


def _devtools_diagnostics(coordinator: Any) -> dict[str, Any]:
    """Недавние данные DevTools для баг-репорта: журнал, изменения, команды, проверка."""
    validation = coordinator.validation_collector.snapshot()
    data = {
        "message_log": list(coordinator.ws_devtools.log)[-DEVTOOLS_MESSAGES:],
        "state_diffs": coordinator.diff_collector.snapshot()[-DEVTOOLS_RECORDS:],
        "commands": coordinator.command_tracker.snapshot()[-DEVTOOLS_RECORDS:],
        "validation": {
            "recent": validation.get("recent", [])[-DEVTOOLS_RECORDS:],
            "by_device": validation.get("by_device", {}),
        },
    }
    return async_redact_data(_truncate_strings(data), DEVTOOLS_REDACT)


def _redact_title(title: str) -> str:
    """Hide the phone number the SMS login puts into the entry title."""
    return _PHONE_RE.sub("**REDACTED**", title)


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
        # OAuth (AuthManager) и SMS-OTP (CsafrontAuthManager) экспонируют
        # разные expiry properties — getattr чтобы не падать AttributeError.
        auth_state = {
            "has_companion": getattr(auth_mgr, "has_companion", None),
            "has_sberid_refresh": getattr(auth_mgr, "has_sberid_refresh", None),
            "has_tokens": getattr(auth_mgr, "has_tokens", None),
            "companion_expires_at": getattr(auth_mgr, "companion_expires_at", None),
            "sberid_expires_at": getattr(auth_mgr, "sberid_expires_at", None),
            "smart_home_expires_at": getattr(auth_mgr, "smart_home_expires_at", None),
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

    # Sber-side scenario context — schema of the UI constructor (`form`),
    # preset system scenarios, and raw user scenarios. Полезно для исследования
    # wire-формата action-типов (например, какие поля принимает
    # `PRONOUNCE_COMMAND.pronounce_data` — есть ли там `text_type`/SSML toggle)
    # и для будущих bug-репортов по новым типам действий Sber.
    scenarios_dump: dict[str, Any] = {}
    if coordinator is not None and getattr(coordinator, "client", None) is not None:
        client = coordinator.client
        for label, awaitable_factory in (
            ("form", client.scenarios.get_form),
            ("system_scenarios", client.scenarios.list_system),
            ("user_scenarios", client.scenarios.list_raw),
        ):
            try:
                scenarios_dump[label] = await awaitable_factory()
            except Exception as err:
                _LOGGER.debug("Diagnostics: scenarios.%s failed: %r", label, err)
                scenarios_dump[f"{label}_error"] = repr(err)

    return {
        "entry": {
            "title": _redact_title(entry.title),
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
        "scenarios": async_redact_data(scenarios_dump, TO_REDACT),
        "devtools": _devtools_diagnostics(coordinator) if coordinator is not None else {},
    }
