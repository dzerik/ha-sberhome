"""WS endpoints для UI tab «🎙 Команда» (TTC: status / ensure / test).

🧪 EXPERIMENTAL. Аналог tts_surrogate, но колонка ВЫПОЛНЯЕТ текст как команду
ассистенту (HEAD_DIALOG_COMMAND), а не озвучивает.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ._common import get_coordinator
from .tts_surrogate import _serialize_speaker

_LOGGER = logging.getLogger(__name__)


@websocket_api.websocket_command({vol.Required("type"): "sberhome/ttc_surrogate/status"})
@websocket_api.async_response
async def ws_status_ttc_surrogate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Per-home состояние TTC-surrogate + список колонок (authoritative discovery)."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_result(msg["id"], {"homes": []})
        return

    from ..sbermap.spec.ha_mapping import resolve_category
    from ..ttc_surrogate.marker import match_surrogate
    from ..ttc_surrogate.service import SBER_SPEAKER_CATEGORY

    scenarios: list[Any] = []
    cache_fallback = False
    try:
        scenarios = await coord.client.scenarios.list()
    except Exception:
        _LOGGER.warning(
            "scenarios.list() failed in ttc status endpoint — falling back to cache",
            exc_info=True,
        )
        cache_fallback = True

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

        sc_id: str | None
        if cache_fallback:
            sc_id = coord.ttc_surrogates.get(home.id)
        else:
            sc_id = next(
                (s.id for s in scenarios if match_surrogate(s, home.id) and s.id),
                None,
            )
            if sc_id:
                coord.ttc_surrogates[home.id] = sc_id
            else:
                coord.ttc_surrogates.pop(home.id, None)

        homes_payload.append(
            {
                "home_id": home.id,
                "name": home.name or "",
                "scenario_id": sc_id,
                "speakers": speakers,
            }
        )
    connection.send_result(msg["id"], {"homes": homes_payload})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/ttc_surrogate/ensure",
        vol.Required("home_id"): str,
    }
)
@websocket_api.async_response
async def ws_ensure_ttc_surrogate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Создать (или найти) TTC-surrogate-сценарий для дома."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_result(msg["id"], {"ok": False, "error": "integration not loaded"})
        return
    try:
        sc_id = await coord.ttc_service.get_surrogate_id(msg["home_id"])
    except Exception as err:
        _LOGGER.exception("ws ensure_ttc_surrogate failed")
        connection.send_result(msg["id"], {"ok": False, "error": str(err)})
        return
    connection.send_result(msg["id"], {"ok": True, "scenario_id": sc_id})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/ttc_surrogate/test",
        vol.Required("home_id"): str,
        vol.Required("message"): str,
        vol.Optional("device_ids"): [str],
    }
)
@websocket_api.async_response
async def ws_test_ttc_surrogate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Тестовая команда: PUT scenario + POST /run + latency measurement."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_result(msg["id"], {"ok": False, "error": "integration not loaded"})
        return
    started = time.monotonic()
    try:
        await coord.ttc_service.send(
            msg["home_id"],
            msg["message"],
            msg.get("device_ids"),
        )
    except Exception as err:
        _LOGGER.exception("ws test_ttc_surrogate failed")
        connection.send_result(msg["id"], {"ok": False, "error": str(err)})
        return
    latency_ms = int((time.monotonic() - started) * 1000)
    connection.send_result(msg["id"], {"ok": True, "latency_ms": latency_ms})
