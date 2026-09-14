"""Settings WS endpoints — get/update + force refresh."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from ..const import CONF_ENABLED_DEVICE_UIDS
from ..settings import SETTINGS_DEFAULTS, SETTINGS_LIMITS, SETTINGS_SCHEMA, read_settings
from ._common import get_config_entry, get_coordinator


@websocket_api.websocket_command({vol.Required("type"): "sberhome/get_settings"})
@callback
def ws_get_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return current settings with their defaults and the bounds enforced on save."""
    entry = get_config_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(
        msg["id"],
        {
            "settings": read_settings(entry.options),
            "defaults": dict(SETTINGS_DEFAULTS),
            "limits": SETTINGS_LIMITS,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/update_settings",
        vol.Required("settings"): dict,
    }
)
@websocket_api.async_response
async def ws_update_settings(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Validate and persist settings; the update listener applies them live.

    An invalid type or out-of-range value rejects the whole request and
    leaves ``entry.options`` untouched.
    """
    entry = get_config_entry(hass)
    if entry is None or get_coordinator(hass) is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        validated = SETTINGS_SCHEMA(msg["settings"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_settings", f"Invalid settings: {err}")
        return
    hass.config_entries.async_update_entry(entry, options={**entry.options, **validated})
    connection.send_result(msg["id"], {"success": True})


CONFIG_FORMAT = "sberhome-config"
"""Marker of an exported panel configuration file."""

CONFIG_VERSION = 1
"""Version of the exported configuration layout."""

_IMPORT_SCHEMA = vol.Schema(
    {
        vol.Required("format"): CONFIG_FORMAT,
        vol.Required("version"): CONFIG_VERSION,
        vol.Required("enabled_device_uids"): [str],
        vol.Required("settings"): SETTINGS_SCHEMA,
    },
    extra=vol.REMOVE_EXTRA,
)


@websocket_api.websocket_command({vol.Required("type"): "sberhome/export_config"})
@callback
def ws_export_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Export the device selection and settings as a portable JSON document.

    The selection is exported as stable device keys (serial numbers where
    available), so the file survives re-pairing and moves between installs.
    """
    entry = get_config_entry(hass)
    if entry is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    connection.send_result(
        msg["id"],
        {
            "format": CONFIG_FORMAT,
            "version": CONFIG_VERSION,
            "enabled_device_uids": list(entry.options.get(CONF_ENABLED_DEVICE_UIDS) or []),
            "settings": read_settings(entry.options),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "sberhome/import_config",
        vol.Required("config"): dict,
    }
)
@websocket_api.async_response
async def ws_import_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Import a configuration exported by :func:`ws_export_config`.

    The whole file is validated first; nothing is written if any part is
    wrong.  Settings are applied live, then the selection is stored through
    the same path as the panel's device list (which reloads the entry).
    """
    entry = get_config_entry(hass)
    coord = get_coordinator(hass)
    if entry is None or coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    try:
        config = _IMPORT_SCHEMA(msg["config"])
    except vol.Invalid as err:
        connection.send_error(msg["id"], "invalid_config", f"Invalid configuration file: {err}")
        return
    hass.config_entries.async_update_entry(entry, options={**entry.options, **config["settings"]})
    await coord.async_import_selection(config["enabled_device_uids"])
    connection.send_result(
        msg["id"], {"success": True, "devices": len(config["enabled_device_uids"])}
    )


@websocket_api.websocket_command({vol.Required("type"): "sberhome/force_refresh"})
@websocket_api.async_response
async def ws_force_refresh(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Force coordinator refresh (immediate REST poll)."""
    coord = get_coordinator(hass)
    if coord is None:
        connection.send_error(msg["id"], "not_loaded", "Integration not loaded")
        return
    await coord.async_request_refresh()
    # Настройки колонок опрашиваются отдельным (часовым) троттлом — форсируем
    # их тоже, иначе правки из приложения Сбера не подтянутся по «Обновить».
    await coord.async_refresh_staros()
    connection.send_result(msg["id"], {"success": True})
