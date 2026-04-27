"""Voice intents WS endpoints — поверх `intents.IntentService`.

Все endpoints возвращают serialized IntentSpec (`spec.to_dict()`) или
ошибки. UI отвечает за форму, обращается через `hass.callWS({type: ...})`.

Endpoints:
- `sberhome/intents/list` — список всех Sber-сценариев как IntentSpec'ов
- `sberhome/intents/get` — один по id
- `sberhome/intents/create` — POST /scenario/v2/scenario
- `sberhome/intents/update` — PUT /scenario/v2/scenario/{id}
- `sberhome/intents/delete` — DELETE
- `sberhome/intents/test` — execute_command (программный запуск)
- `sberhome/intents/schema` — registry schema для динамической формы
- `sberhome/intents/devices_for_picker` — устройства для UI device-picker'а,
  фильтр по category, БЕЗ HA enabled_device_ids фильтра
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..intents import (
    IntentService,
    IntentSpec,
    schema_dict,
)
from ..sbermap import resolve_category
from ._common import get_coordinator


def _service(hass: HomeAssistant) -> IntentService | None:
    coord = get_coordinator(hass)
    return IntentService(coord) if coord is not None else None


# ---------------------------------------------------------------------------
# list / get / schema (read-only)
# ---------------------------------------------------------------------------


@websocket_api.websocket_command({vol.Required("type"): "sberhome/intents/list"})
@websocket_api.async_response
async def ws_list_intents(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    service = _service(hass)
    if service is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        specs = await service.list_intents()
    except Exception as err:  # noqa: BLE001 — surface to UI
        connection.send_error(msg["id"], "fetch_failed", str(err))
        return
    connection.send_result(msg["id"], {"intents": [s.to_dict() for s in specs]})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/intents/get",
        vol.Required("intent_id"): str,
    }
)
@websocket_api.async_response
async def ws_get_intent(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    service = _service(hass)
    if service is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    intent_id = msg["intent_id"]
    try:
        spec = await service.get_intent(intent_id)
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "fetch_failed", str(err))
        return
    if spec is None:
        connection.send_error(msg["id"], "not_found", f"Intent {intent_id} not found")
        return
    connection.send_result(msg["id"], spec.to_dict())


@websocket_api.websocket_command({vol.Required("type"): "sberhome/intents/schema"})
@websocket_api.async_response
async def ws_intent_schema(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Возвращает action-types schema для UI динамического render'а формы.

    Не требует coordinator (read-only схема), но проверяем для consistency.
    """
    if get_coordinator(hass) is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(msg["id"], {"action_types": schema_dict()})


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


_INTENT_SPEC_SCHEMA = vol.Schema(
    {
        vol.Optional("id"): vol.Any(str, None),
        vol.Required("name"): vol.All(str, vol.Length(min=1, max=128)),
        vol.Required("phrases"): [str],
        vol.Required("actions"): [dict],
        vol.Optional("enabled", default=True): bool,
        vol.Optional("description", default=""): str,
        vol.Optional("raw_extras", default={}): dict,
    },
    extra=vol.ALLOW_EXTRA,  # будем игнорить лишние поля от UI без падения
)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/intents/create",
        vol.Required("spec"): _INTENT_SPEC_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_create_intent(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    service = _service(hass)
    if service is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    spec = IntentSpec.from_dict(msg["spec"])
    try:
        result = await service.create_intent(spec)
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "create_failed", str(err))
        return
    connection.send_result(msg["id"], result.to_dict())


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/intents/update",
        vol.Required("intent_id"): str,
        vol.Required("spec"): _INTENT_SPEC_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_update_intent(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    service = _service(hass)
    if service is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    spec = IntentSpec.from_dict(msg["spec"])
    try:
        result = await service.update_intent(msg["intent_id"], spec)
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "update_failed", str(err))
        return
    connection.send_result(msg["id"], result.to_dict())


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/intents/delete",
        vol.Required("intent_id"): str,
    }
)
@websocket_api.async_response
async def ws_delete_intent(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    service = _service(hass)
    if service is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        await service.delete_intent(msg["intent_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "delete_failed", str(err))
        return
    connection.send_result(msg["id"], {"success": True})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/intents/test",
        vol.Required("intent_id"): str,
    }
)
@websocket_api.async_response
async def ws_test_intent(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Программный запуск сценария (как «Test now» кнопка в UI)."""
    service = _service(hass)
    if service is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        result = await service.test_intent(msg["intent_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "test_failed", str(err))
        return
    connection.send_result(msg["id"], {"success": True, "sber_response": result})


# ---------------------------------------------------------------------------
# Device picker — extensible filter
# ---------------------------------------------------------------------------


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/intents/devices_for_picker",
        vol.Optional("category"): vol.Any(str, [str]),
    }
)
def ws_devices_for_picker(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Список устройств для UI device-picker'а в форме action data.

    КЛЮЧЕВОЕ ОТЛИЧИЕ от обычного `sberhome/get_devices`: возвращает ВСЕ
    Sber-устройства независимо от HA `enabled_device_ids`. Пользователь
    может выбрать колонку для TTS-action'а даже если она не подключена
    в HA — Sber-сценарий выполнится в облаке без участия HA.

    Args:
        category: optional фильтр. str или list[str], сопоставляется через
            `resolve_category(image_set_type)`. Например `"sber_speaker"`
            для TTS-pick'а.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    category_filter: set[str] | None = None
    if "category" in msg:
        raw = msg["category"]
        if isinstance(raw, str):
            category_filter = {raw}
        elif isinstance(raw, list):
            category_filter = {str(c) for c in raw if c}

    out: list[dict[str, Any]] = []
    for device_id, dto in coord.state_cache.get_all_devices().items():
        cat = resolve_category(dto.image_set_type)
        if category_filter is not None and cat not in category_filter:
            continue
        out.append(
            {
                "device_id": device_id,
                "name": dto.display_name or device_id,
                "category": cat,
                "image_set_type": dto.image_set_type,
                "model": dto.device_info.model if dto.device_info else None,
                "room": coord.state_cache.device_room(device_id),
            }
        )
    # Стабильная сортировка по имени для UI.
    out.sort(key=lambda d: (d["category"] or "", d["name"] or ""))
    connection.send_result(msg["id"], {"devices": out})


__all__ = [
    "ws_create_intent",
    "ws_delete_intent",
    "ws_devices_for_picker",
    "ws_get_intent",
    "ws_intent_schema",
    "ws_list_intents",
    "ws_test_intent",
    "ws_update_intent",
]
