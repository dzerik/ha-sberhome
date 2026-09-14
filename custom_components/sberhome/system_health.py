"""Сводка SberHome на странице «Сведения о системе» Home Assistant.

Короткая, всегда доступная сводка для баг-репорта: её копируют целиком,
не открывая панель. Поэтому только значения — без токенов, телефона и
имён устройств.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import GATEWAY_BASE_URL
from .health import compute_health
from .repairs import collect_health_inputs
from .websocket_api._common import get_config_entry, get_coordinator


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    """Зарегистрировать сводку и панель SberHome как страницу управления."""
    register.async_register_info(system_health_info, "/sberhome")


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Значения для страницы «Сведения о системе».

    Returns:
        Плоский словарь; ``can_reach_gateway`` проверяется лениво самим HA.
    """
    info: dict[str, Any] = {
        "can_reach_gateway": system_health.async_check_can_reach_url(hass, GATEWAY_BASE_URL)
    }
    coord = get_coordinator(hass)
    entry = get_config_entry(hass)
    if coord is None or entry is None:
        info["state"] = "not_loaded"
        return info
    health = compute_health(collect_health_inputs(hass, coord))
    info.update(
        {
            "state": health["score"],
            "problems": ", ".join(issue["code"] for issue in health["issues"]) or "—",
            "websocket": "connected" if coord.ws_connected else "disconnected",
            "last_poll": coord.last_polling_at and int(coord.last_polling_at),
            "failed_updates_in_a_row": getattr(coord, "consecutive_failures", 0),
            "devices_total": len(coord.devices),
            "devices_enabled": len(coord.enabled_device_ids)
            if coord.enabled_device_ids is not None
            else len(coord.devices),
        }
    )
    return info
