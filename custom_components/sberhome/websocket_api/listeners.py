"""WS endpoint `sberhome/listeners/list` — read-only список YAML listeners."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def _serialize_filter(f: Any) -> dict[str, Any]:
    """ListenerFilter → JSON-friendly dict для UI."""
    return {
        "trigger_types": sorted(f.trigger_types) if f.trigger_types is not None else None,
        "scenario_name": f.scenario_name,
        "scenario_id": f.scenario_id,
        "home_id": f.home_id,
    }


def _serialize_spec(spec: Any) -> dict[str, Any]:
    """ListenerSpec → JSON-friendly dict для UI."""
    return {
        "slug": spec.slug,
        "name": spec.name,
        "enabled": spec.enabled,
        "description": spec.description,
        "filter": _serialize_filter(spec.filter),
        "last_fired_at": spec.last_fired_at,
    }


@websocket_api.websocket_command({vol.Required("type"): "sberhome/listeners/list"})
@websocket_api.async_response
async def ws_list_listeners(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Вернуть JSON-friendly список всех зарегистрированных listeners."""
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        connection.send_result(msg["id"], {"listeners": []})
        return

    coord = entries[0].runtime_data
    if not hasattr(coord, "listener_registry"):
        connection.send_result(msg["id"], {"listeners": []})
        return

    listeners = [_serialize_spec(s) for s in coord.listener_registry.list()]
    connection.send_result(msg["id"], {"listeners": listeners})
