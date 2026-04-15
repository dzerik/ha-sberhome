"""The SberHome integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .api import HomeAPI, SberAPI, async_init_ssl
from .const import LOGGER
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .exceptions import SberAuthError, SberConnectionError, SberSmartHomeError

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
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


async def async_setup_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> bool:
    """Set up SberHome from a config entry."""
    await async_init_ssl(hass)
    sber = SberAPI(token=entry.data["token"])
    home = HomeAPI(sber)

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

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> None:
    """Clean up when a config entry is removed."""
    from .auth_state import pending_auth_flows

    pending_auth_flows.pop(entry.entry_id, None)


async def _close_clients(sber: SberAPI, home: HomeAPI) -> None:
    """Close API clients on setup failure."""
    await home.aclose()
    await sber.aclose()
