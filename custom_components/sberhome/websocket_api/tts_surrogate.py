"""WS endpoints для UI tab «🔊 TTS» (status / ensure / test).

🧪 EXPERIMENTAL. См. CHANGELOG v5.6.0 + spec.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _get_coord(hass: HomeAssistant) -> Any | None:
    """Get loaded SberHome coordinator with tts_service attached.

    Uses `async_loaded_entries` (not `async_entries`) to skip stale/disabled
    entries without `runtime_data`.
    """
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        return None
    coord = entries[0].runtime_data
    if coord is None or not hasattr(coord, "tts_service"):
        return None
    return coord


def _name_to_str(name: Any) -> str:
    """Достать человекочитаемое имя из ``DeviceDto.name`` (NameDto или None).

    Sber wire даёт `name: {name: "Люстра", defaultName: "", names: {}}`
    через ``NameDto``. Plain-string fallback тоже поддерживаем (legacy).
    """
    if name is None:
        return ""
    if isinstance(name, str):
        return name
    # NameDto: pick .name → .default_name → ""
    inner = getattr(name, "name", None)
    if inner:
        return str(inner)
    default = getattr(name, "default_name", None)
    if default:
        return str(default)
    return ""


def _serialize_speaker(dto: Any, device_id: str) -> dict[str, Any]:
    name = _name_to_str(getattr(dto, "name", None)) or device_id
    online = None
    reported = getattr(dto, "reported_value", None)
    if callable(reported):
        online = reported("online")
    return {"id": device_id, "name": name, "online": online}


@websocket_api.websocket_command({vol.Required("type"): "sberhome/tts_surrogate/status"})
@websocket_api.async_response
async def ws_status_tts_surrogate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Per-home состояние surrogate + список колонок."""
    coord = _get_coord(hass)
    if coord is None:
        connection.send_result(msg["id"], {"homes": []})
        return

    from ..sbermap.spec.ha_mapping import resolve_category
    from ..tts_surrogate.service import SBER_SPEAKER_CATEGORY

    cache = coord.state_cache
    devices = cache.get_all_devices()
    homes_payload = []
    for home in cache.get_homes():
        if not home.id:
            continue
        speakers = []
        for device_id, dto in devices.items():
            if cache.device_home_id(device_id) != home.id:
                continue
            slug = None
            if getattr(dto, "full_categories", None):
                first = dto.full_categories[0]
                slug = getattr(first, "slug", None)
            cat = resolve_category(dto.image_set_type, slug=slug)
            if cat == SBER_SPEAKER_CATEGORY:
                speakers.append(_serialize_speaker(dto, device_id))
        homes_payload.append(
            {
                "home_id": home.id,
                "name": home.name or "",
                "scenario_id": coord.tts_surrogates.get(home.id),
                "speakers": speakers,
            }
        )
    connection.send_result(msg["id"], {"homes": homes_payload})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/tts_surrogate/ensure",
        vol.Required("home_id"): str,
    }
)
@websocket_api.async_response
async def ws_ensure_tts_surrogate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Создать (или найти) surrogate-сценарий для указанного дома."""
    coord = _get_coord(hass)
    if coord is None:
        connection.send_result(msg["id"], {"ok": False, "error": "integration not loaded"})
        return
    try:
        sc_id = await coord.tts_service.get_surrogate_id(msg["home_id"])
    except Exception as err:  # noqa: BLE001 — best-effort surface to UI
        _LOGGER.exception("ws ensure_tts_surrogate failed")
        connection.send_result(msg["id"], {"ok": False, "error": str(err)})
        return
    connection.send_result(msg["id"], {"ok": True, "scenario_id": sc_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/tts_surrogate/test",
        vol.Required("home_id"): str,
        vol.Required("message"): str,
        vol.Optional("device_ids"): [str],
    }
)
@websocket_api.async_response
async def ws_test_tts_surrogate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Тестовая озвучка: PUT scenario + POST /run + latency measurement."""
    coord = _get_coord(hass)
    if coord is None:
        connection.send_result(msg["id"], {"ok": False, "error": "integration not loaded"})
        return
    started = time.monotonic()
    try:
        await coord.tts_service.send(
            msg["home_id"],
            msg["message"],
            msg.get("device_ids"),
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.exception("ws test_tts_surrogate failed")
        connection.send_result(msg["id"], {"ok": False, "error": str(err)})
        return
    latency_ms = int((time.monotonic() - started) * 1000)
    connection.send_result(msg["id"], {"ok": True, "latency_ms": latency_ms})
