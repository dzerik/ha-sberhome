"""Shared helpers for SberHome panel WebSocket API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import DOMAIN

if TYPE_CHECKING:
    from ..coordinator import SberHomeCoordinator


def get_config_entry(hass: HomeAssistant) -> ConfigEntry | None:
    """Return the first loaded config entry for SberHome (or None)."""
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    return entries[0] if entries else None


def get_coordinator(hass: HomeAssistant) -> SberHomeCoordinator | None:
    """Return active `SberHomeCoordinator` from `ConfigEntry.runtime_data`."""
    entry = get_config_entry(hass)
    if entry is None or not hasattr(entry, "runtime_data") or entry.runtime_data is None:
        return None
    return entry.runtime_data
