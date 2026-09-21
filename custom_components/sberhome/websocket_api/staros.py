"""WS endpoint настроек умных колонок (новый канал /v18).

Отдаёт панели список колонок и их настройки (эквалайзер/тумблеры/пресеты),
уже разложенные координатором в дескрипторы `StarosSettingEntity`. Панель
рисует таб «Колонки»: инфо + управление через штатные HA-сущности (в ответе
есть `entity_id`).
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from ..const import DOMAIN
from ._common import get_coordinator


def _entity_id(registry: er.EntityRegistry, platform: str, unique_id: str) -> str | None:
    """entity_id по (domain-platform, DOMAIN, unique_id) или None."""
    return registry.async_get_entity_id(platform, DOMAIN, unique_id)


def _spec_to_dict(spec: Any, entity_id: str | None) -> dict[str, Any]:
    """StarosSettingEntity → плоский dict для панели."""
    return {
        "entity_id": entity_id,
        "unique_id": spec.unique_id,
        "name": spec.name,
        "platform": spec.platform.value,
        "node_id": spec.node_id,
        "state": spec.state,
        "options": list(spec.options),
        "option_titles": dict(spec.option_titles),
        "min": spec.min_value,
        "max": spec.max_value,
        "step": spec.step,
        "unit": spec.unit,
        "eq_group": spec.eq_group,
        "eq_role": spec.eq_role,
        "eq_band_index": spec.eq_band_index,
        "eq_frequency": spec.eq_frequency,
    }


@websocket_api.websocket_command({vol.Required("type"): "sberhome/staros/list"})
@callback
def ws_staros_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Список колонок + их настройки (эквалайзер/тумблеры) из канала /v18."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return

    registry = er.async_get(hass)
    devices = [
        {
            "serial": dev.serial_number,
            "product": dev.product,
            "name": dev.name,
        }
        for dev in coord.staros_devices
    ]
    settings: dict[str, list[dict[str, Any]]] = {}
    for serial, specs in coord.staros_settings_entities.items():
        settings[serial] = [
            _spec_to_dict(s, _entity_id(registry, s.platform.value, s.unique_id)) for s in specs
        ]

    connection.send_result(
        msg["id"],
        {
            "available": coord.has_staros_settings(),
            "speaker_present": coord.staros_speaker_present(),
            "devices": devices,
            "settings": settings,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/staros/dump",
        vol.Optional("serial"): str,
    }
)
@websocket_api.async_response
async def ws_staros_dump(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Сырой дамп дерева настроек колонок (/v18) — для диагностики/фикстур.

    Живой запрос к каналу настроек: возвращает исходный JSON экрана как есть,
    чтобы по нему добавлять поддержку новых моделей колонок. Опциональный
    `serial` ограничивает одной колонкой.
    """
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    if not coord.has_staros_settings():
        connection.send_error(
            msg["id"],
            "unavailable",
            "Канал настроек колонок недоступен (вход по SMS или требуется reauth)",
        )
        return
    dump = await coord.async_dump_staros_raw(msg.get("serial"))
    connection.send_result(msg["id"], {"dump": dump})
