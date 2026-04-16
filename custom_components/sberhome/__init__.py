"""The SberHome integration."""

from __future__ import annotations

import pathlib

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from ._ha_token_store import HATokenStore
from .api import HomeAPI, SberAPI, async_init_ssl
from .const import DOMAIN, LOGGER
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .exceptions import SberAuthError, SberConnectionError, SberSmartHomeError
from .websocket_api import async_setup_websocket_api

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.FAN,
    Platform.HUMIDIFIER,
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VACUUM,
]

_PANEL_URL_PATH = "sberhome"
_PANEL_STATIC_PATH = "/sberhome_panel"


async def async_setup_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> bool:
    """Set up SberHome from a config entry."""
    await async_init_ssl(hass)
    sber = SberAPI(token=entry.data["token"])
    # HATokenStore persist'ит companion-токены в config_entry.data — переживает
    # перезагрузку HA, не требуя нового companion exchange при каждом запуске.
    token_store = HATokenStore(hass, entry)
    home = HomeAPI(sber, token_store=token_store)

    coordinator = SberHomeCoordinator(hass, entry, sber, home)

    try:
        await coordinator.async_config_entry_first_refresh()
    except (ConfigEntryNotReady, ConfigEntryAuthFailed):
        await _close_clients(sber, home)
        raise
    except SberAuthError as err:
        await _close_clients(sber, home)
        raise ConfigEntryAuthFailed(
            f"Authentication failed: {err}"
        ) from err
    except (SberConnectionError, SberSmartHomeError) as err:
        await _close_clients(sber, home)
        raise ConfigEntryNotReady(
            f"Failed to connect: {err}"
        ) from err
    except Exception as err:
        await _close_clients(sber, home)
        LOGGER.exception("Unexpected error setting up SberHome")
        raise ConfigEntryNotReady(
            f"Unexpected error: {err}"
        ) from err

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Panel + WS API (PR #12) — идемпотентно, для всех config entries shared.
    async_setup_websocket_api(hass)
    await _async_register_panel(hass)

    # Update listener: при изменении options (e.g. enabled_device_ids через
    # panel) — релоадим entry, чтобы платформы пересоздали entities.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    # Если последняя SberHome-запись уходит — снимаем panel.
    if unloaded and not hass.config_entries.async_loaded_entries(DOMAIN):
        try:
            async_remove_panel(hass, _PANEL_URL_PATH)
        except Exception:  # noqa: BLE001 — best-effort
            LOGGER.debug("Panel %s already removed", _PANEL_URL_PATH)
    return unloaded


async def async_remove_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> None:
    """Clean up when a config entry is removed."""
    from .auth_state import pending_auth_flows

    pending_auth_flows.pop(entry.entry_id, None)


async def _async_options_updated(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> None:
    """Reload entry on options change (e.g. enabled_device_ids from panel).

    Reload пересоздаст coordinator и платформы — entities появятся/исчезнут
    в соответствии с новым enabled set.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register frontend panel + static path (idempotent)."""
    marker = f"{DOMAIN}_panel_registered"
    if hass.data.get(marker):
        return

    panel_dir = str(pathlib.Path(__file__).parent / "www")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(_PANEL_STATIC_PATH, panel_dir, cache_headers=False)]
    )

    from .const import VERSION  # avoid import cycle

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="SberHome",
        sidebar_icon="mdi:home-assistant",
        frontend_url_path=_PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "sberhome-panel",
                "module_url": f"{_PANEL_STATIC_PATH}/sberhome-panel.js?v={VERSION}",
            }
        },
        require_admin=False,
    )
    hass.data[marker] = True


async def _close_clients(sber: SberAPI, home: HomeAPI) -> None:
    """Close API clients on setup failure."""
    await home.aclose()
    await sber.aclose()
