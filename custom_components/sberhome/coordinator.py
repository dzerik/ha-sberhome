"""DataUpdateCoordinator for SberHome."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import HomeAPI, SberAPI
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER
from .exceptions import SberApiError, SberAuthError, SberConnectionError, SberSmartHomeError


type SberHomeConfigEntry = ConfigEntry[SberHomeCoordinator]


class SberHomeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching SberHome data."""

    config_entry: SberHomeConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SberHomeConfigEntry,
        sber_api: SberAPI,
        home_api: HomeAPI,
    ) -> None:
        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.sber_api = sber_api
        self.home_api = home_api
        self._user_update_interval = timedelta(seconds=scan_interval)

    async def _async_setup(self) -> None:
        """Perform initial setup on first coordinator refresh."""
        LOGGER.debug("Coordinator initial setup complete")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the SberHome API."""
        try:
            await self.home_api.update_devices_cache()
            devices = self.home_api.get_cached_devices()
            LOGGER.debug("Updated %d devices from API", len(devices))
            # Восстанавливаем пользовательский интервал после успешного опроса
            # (мог быть понижен до retry_after при 429).
            if self.update_interval != self._user_update_interval:
                self.update_interval = self._user_update_interval
            return devices
        except SberAuthError as err:
            LOGGER.warning("Authentication failed during update: %s", err)
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except SberApiError as err:
            if err.retry_after:
                LOGGER.warning(
                    "Rate limited, retry after %ds: %s", err.retry_after, err
                )
                self.update_interval = timedelta(seconds=err.retry_after)
            raise UpdateFailed(
                f"API error: {err}"
            ) from err
        except (SberConnectionError, SberSmartHomeError) as err:
            LOGGER.warning("API communication error during update: %s", err)
            raise UpdateFailed(
                f"Error communicating with API: {err}"
            ) from err

    async def async_shutdown(self) -> None:
        """Close API clients on shutdown."""
        await super().async_shutdown()
        await self.home_api.aclose()
        await self.sber_api.aclose()
