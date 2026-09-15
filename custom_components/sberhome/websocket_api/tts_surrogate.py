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

from ..action_errors import async_error_message
from ._common import get_coordinator

_LOGGER = logging.getLogger(__name__)


def _name_to_str(name: Any) -> str:
    """Достать человекочитаемое имя из ``DeviceDto.name`` (``NameDto`` или None).

    Sber wire даёт `name: {name: "Люстра", defaultName: "", names: {}}`;
    пустое имя заменяется именем по умолчанию.
    """
    if name is None:
        return ""
    return str(name.name or name.default_name or "")


def _serialize_speaker(dto: Any, device_id: str) -> dict[str, Any]:
    """DeviceDto + id → JSON-friendly dict для UI."""
    name = _name_to_str(getattr(dto, "name", None)) or device_id
    # `reported_value` — реальный method на DeviceDto; для unit-test mocks
    # (где dto = MagicMock) тоже работает по сигнатуре.
    online = dto.reported_value("online") if hasattr(dto, "reported_value") else None
    return {"id": device_id, "name": name, "online": online}


@websocket_api.websocket_command({vol.Required("type"): "sberhome/tts_surrogate/status"})
@websocket_api.async_response
async def ws_status_tts_surrogate(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Per-home состояние surrogate + список колонок.

    Authoritative discovery: дёргаем ``scenarios.list()`` и матчим по marker'у.
    Кеш ``coord.tts_surrogates`` подсинхронизировывается с результатом —
    если юзер вручную удалил surrogate в приложении «Салют!», UI больше
    не покажет «✓ создан» по stale-кешу.

    Fallback: если ``scenarios.list()`` упал (network), используем кеш —
    UI получает потенциально stale state, но не падает.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_result(msg["id"], {"homes": []})
        return

    from ..sbermap import resolve_device_category
    from ..tts_surrogate.marker import match_surrogate
    from ..tts_surrogate.service import SBER_SPEAKER_CATEGORY

    # Authoritative list — корректирует stale cache. Best-effort fallback на
    # кеш при ошибке list'а: лучше показать stale state чем падать.
    scenarios: list[Any] = []
    cache_fallback = False
    try:
        scenarios = await coord.client.scenarios.list()
    except Exception:
        _LOGGER.warning(
            "scenarios.list() failed in status endpoint — falling back to cache",
            exc_info=True,
        )
        cache_fallback = True

    cache = coord.state_cache
    devices = cache.get_all_devices()
    homes_payload = []
    # У домов из кэша id всегда непустой — без id StateCache их не хранит.
    for home in cache.get_homes():
        speakers = [
            _serialize_speaker(dto, device_id)
            for device_id, dto in devices.items()
            if cache.device_home_id(device_id) == home.id
            and resolve_device_category(dto) == SBER_SPEAKER_CATEGORY
        ]

        # Resolve scenario_id authoritatively (или из кеша при fallback'е).
        sc_id: str | None
        if cache_fallback:
            sc_id = coord.tts_surrogates.get(home.id)
        else:
            sc_id = next(
                (s.id for s in scenarios if match_surrogate(s, home.id) and s.id),
                None,
            )
            # Sync cache с authoritative результатом.
            if sc_id:
                coord.tts_surrogates[home.id] = sc_id
            else:
                coord.tts_surrogates.pop(home.id, None)

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
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_result(msg["id"], {"ok": False, "error": "integration not loaded"})
        return
    try:
        sc_id = await coord.tts_service.get_surrogate_id(msg["home_id"])
    except Exception as err:
        _LOGGER.exception("ws ensure_tts_surrogate failed")
        connection.send_result(
            msg["id"], {"ok": False, "error": await async_error_message(hass, err)}
        )
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
    coord = get_coordinator(hass)
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
    except Exception as err:
        _LOGGER.exception("ws test_tts_surrogate failed")
        connection.send_result(
            msg["id"], {"ok": False, "error": await async_error_message(hass, err)}
        )
        return
    latency_ms = int((time.monotonic() - started) * 1000)
    connection.send_result(msg["id"], {"ok": True, "latency_ms": latency_ms})
