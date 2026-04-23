"""Shared helpers for SberHome panel WebSocket API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from ..const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry

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


def _identifier_candidates(coord: SberHomeCoordinator, sber_device_id: str) -> list[str]:
    """Возможные identifier-строки для HA device_registry.

    В `entity.SberHomeEntity.device_info` identifier строится как
    `serial_number → dto.id → sber_device_id`. Ищем по всем трём
    кандидатам, т.к. выбор зависит от того, что непустое в DTO.
    """
    candidates: list[str] = []
    dto = coord.devices.get(sber_device_id)
    if dto is not None:
        if dto.serial_number:
            candidates.append(dto.serial_number)
        if dto.id and dto.id not in candidates:
            candidates.append(dto.id)
    if sber_device_id not in candidates:
        candidates.append(sber_device_id)
    return candidates


def find_ha_device(
    hass: HomeAssistant,
    coord: SberHomeCoordinator,
    sber_device_id: str,
) -> DeviceEntry | None:
    """Найти HA device_registry entry по Sber device_id.

    Identifier устройства в HA берётся из serial_number (если есть) или
    dto.id, а не из sber_device_id напрямую. Эта функция перебирает все
    возможные кандидаты и возвращает первое совпадение.
    """
    device_registry = dr.async_get(hass)
    for ident in _identifier_candidates(coord, sber_device_id):
        ha_device = device_registry.async_get_device(identifiers={(DOMAIN, ident)})
        if ha_device is not None:
            return ha_device
    return None
