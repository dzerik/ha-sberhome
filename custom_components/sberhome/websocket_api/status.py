"""Status WS endpoint — token, WS connection, polling stats, errors."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..conflict import detect_conflicts
from ._common import get_config_entry, get_coordinator


def _read_integration_version() -> str | None:
    """Прочитать version из manifest.json — для отображения в UI шапке."""
    try:
        manifest_path = Path(__file__).resolve().parent.parent / "manifest.json"
        with manifest_path.open() as f:
            return json.load(f).get("version")
    except Exception:
        return None


# Кэшируем — manifest не меняется во время runtime.
_VERSION = _read_integration_version()


def _selection_health(coord) -> dict:
    """Сколько выбранных устройств сопоставилось с текущей выдачей.

    Несопоставленное — не обязательно поломка: устройство может быть офлайн.
    Но именно из этого числа видно, что выбор протух целиком.
    """
    stored = coord.enabled_device_uids
    if stored is None:
        return {"stored": None, "resolved": None, "unresolved": 0}
    resolved = coord.enabled_device_ids or set()
    return {
        "stored": len(stored),
        "resolved": len(resolved),
        "unresolved": max(len(stored) - len(resolved), 0),
    }


@websocket_api.websocket_command({vol.Required("type"): "sberhome/get_status"})
@callback
def ws_get_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return SberHome integration health status."""
    coord = get_coordinator(hass)
    entry = get_config_entry(hass)
    if coord is None or entry is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    # Tokens живут в HomeAPI.AuthManager (после перехода на aiosber 2.6.0).
    # Два разных типа auth-flow: OAuth (AuthManager) — два токена sberid+companion;
    # SMS-OTP (CsafrontAuthManager) — единый smart_home_token. getattr-доступ,
    # чтобы status не падал AttributeError при отсутствующих полях.
    auth = coord.auth_manager
    sberid_expires = getattr(auth, "sberid_expires_at", None)
    companion_expires = getattr(auth, "companion_expires_at", None)
    smart_home_expires = getattr(auth, "smart_home_expires_at", None)

    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "version": _VERSION,
            "devices_total": len(coord.devices),
            "devices_enabled": (
                len(coord.enabled_device_ids)
                if coord.enabled_device_ids is not None
                else len(coord.devices)
            ),
            # Сохранённых ключей может быть больше, чем сопоставленных: часть
            # устройств бывает офлайн или в другом доме. Раньше такое
            # расхождение было невидимым, и «пропал выбор» выяснялось только по
            # исчезнувшим сущностям.
            "selection": _selection_health(coord),
            "registry": {
                "maintenance_failures": getattr(coord, "registry_maintenance_failures", 0),
                "last_prune_removed": getattr(coord, "last_prune_removed", 0),
                "migration_pending": getattr(coord, "selection_migration_pending", False),
            },
            "polling": {
                "last_at": coord.last_polling_at,
                "count": coord.polling_count,
                "interval_seconds": coord.update_interval.total_seconds()
                if coord.update_interval
                else None,
                "last_success": coord.last_update_success,
            },
            "ws": {
                "connected": coord.ws_connected,
                "last_message_at": coord.last_ws_message_at,
                "message_count": coord.ws_message_count,
            },
            "tokens": {
                "sberid_expires_at": sberid_expires,
                "companion_expires_at": companion_expires,
                "smart_home_expires_at": smart_home_expires,
            },
            "error_count": coord.error_count,
            # Домены параллельно установленных Sber-интеграций (issue #10).
            # Панель рисует предупреждающий баннер если список непустой.
            "conflict_integrations": detect_conflicts(hass),
            # Настройки умных колонок: есть ли колонка и доступен ли канал
            # управления её настройками. Панель предупреждает, когда колонка
            # есть, а канал недоступен (вход по SMS).
            "speaker_present": coord.staros_speaker_present(),
            "staros_settings_available": coord.has_staros_settings(),
        },
    )
