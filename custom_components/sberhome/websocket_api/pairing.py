"""Pairing WS endpoints — обёртки над PairingAPI для UI panel.

Это thin-shim'ы: вся бизнес-логика остаётся на стороне Sber Gateway,
WS endpoints только передают payload и переводят ошибки в WS errors.

Полноценный config_flow с Matter wizard'ом не реализован — для него
нужно физическое железо для теста и UX-дизайн. Эти endpoints дают
панели minimum-required surface, поверх которой можно нарастить
custom Lit-based «Add device» wizard в будущем.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from ..aiosber.api import PairingAPI
from ..aiosber.dto import DeviceToPairingBody
from ._common import get_coordinator


def _api(coord) -> PairingAPI:
    """Use SberClient facade — единая точка входа во все Sber API.

    Раньше строили PairingAPI напрямую поверх transport; теперь идём
    через coordinator.client.pairing, как требует CLAUDE.md (фасад
    SberClient — public entry point для 80% задач).
    """
    return coord.client.pairing


@websocket_api.websocket_command({vol.Required("type"): "sberhome/pairing/wifi_credentials"})
@websocket_api.async_response
async def ws_get_wifi_credentials(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """GET /credentials/wifi — bootstrap SSID + temp password."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        creds = await _api(coord).get_wifi_credentials()
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "fetch_failed", str(err))
        return
    connection.send_result(msg["id"], creds)


@websocket_api.websocket_command({vol.Required("type"): "sberhome/pairing/matter_categories"})
@websocket_api.async_response
async def ws_list_matter_categories(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """GET /devices/categories/matter — каталог Matter-категорий."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        cats = await _api(coord).list_matter_categories()
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "fetch_failed", str(err))
        return
    connection.send_result(msg["id"], {"categories": cats})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/pairing/start",
        vol.Required("pairing_type"): vol.In(["wifi", "zigbee", "matter"]),
        vol.Optional("image_set_type"): str,
        vol.Optional("device_id"): str,
        vol.Optional("timeout"): int,
        vol.Optional("extra"): dict,
    }
)
@websocket_api.async_response
async def ws_start_pairing(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """POST /devices/pairing — поставить новое устройство в pairing mode."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    body = DeviceToPairingBody(
        device_id=msg.get("device_id"),
        image_set_type=msg.get("image_set_type"),
        pairing_type=msg["pairing_type"],
        timeout=msg.get("timeout"),
        extra=msg.get("extra"),
    )
    try:
        result = await _api(coord).start_pairing(body)
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "pairing_failed", str(err))
        return
    connection.send_result(msg["id"], result)


def _matter_step_command(name: str, method_attr: str):
    """Factory: одинаковая обёртка над `matter_*` методами."""

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"sberhome/pairing/matter_{name}",
            vol.Optional("payload"): dict,
        }
    )
    @websocket_api.async_response
    async def handler(
        hass: HomeAssistant,
        connection: websocket_api.ActiveConnection,
        msg: dict[str, Any],
    ) -> None:
        coord = get_coordinator(hass)
        if coord is None:
            connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
            return
        api = _api(coord)
        method = getattr(api, method_attr)
        try:
            result = await method(msg.get("payload") or {})
        except Exception as err:  # noqa: BLE001
            connection.send_error(msg["id"], "matter_failed", str(err))
            return
        connection.send_result(msg["id"], result)

    handler.__name__ = f"ws_matter_{name}"
    return handler


ws_matter_attestation = _matter_step_command("attestation", "matter_attestation")
ws_matter_noc = _matter_step_command("noc", "matter_request_noc")
ws_matter_complete = _matter_step_command("complete", "matter_complete")
ws_matter_connect_controller = _matter_step_command(
    "connect_controller", "matter_connect_controller"
)
ws_matter_connect_device = _matter_step_command("connect_device", "matter_connect_device")
