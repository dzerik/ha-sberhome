"""SberHome firmware update entities — sourced from `/inventory/ota-upgrades`.

Per-device `UpdateEntity` показывает:
- `installed_version` — `device.sw_version` из tree.
- `latest_version` — `available_version` из inventory upgrade record.
- `release_summary` — `release_notes` если есть.

Установка обновления (push install) пока не реализована — Sber API
не даёт generic install endpoint, OTA процесс полностью server-side
(scheduled rollout). Entity отрабатывает как «info-only» индикатор,
который HA UI показывает золотым колокольчиком когда `installed != latest`.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[UpdateEntity] = []
    # Per-enabled-device firmware updater. Создаётся даже без pending
    # update — installed=latest, и HA отрисует «Up-to-date».
    for device_id in coordinator.devices:
        entities.append(SberFirmwareUpdate(coordinator, device_id))
    async_add_entities(entities)


class SberFirmwareUpdate(SberBaseEntity, UpdateEntity):
    """Firmware version mirror + pending-update indicator."""

    _attr_supported_features = UpdateEntityFeature(0)
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id, "firmware")
        self._attr_name = "Firmware"
        self._attr_has_entity_name = True
        self._attr_icon = "mdi:cellphone-arrow-down"

    @property
    def _device(self):
        return self.coordinator.devices.get(self._device_id)

    @property
    def _upgrade(self) -> dict[str, Any] | None:
        info = self.coordinator.ota_upgrades.get(self._device_id)
        return info if isinstance(info, dict) else None

    @property
    def installed_version(self) -> str | None:
        dto = self._device
        return dto.sw_version if dto else None

    @property
    def latest_version(self) -> str | None:
        upgrade = self._upgrade
        if upgrade is None:
            # Если в inventory нет записи — считаем что прошивка на актуальной
            # версии (HA покажет «Up to date»).
            return self.installed_version
        return (
            upgrade.get("available_version")
            or upgrade.get("latest_version")
            or self.installed_version
        )

    @property
    def release_summary(self) -> str | None:
        upgrade = self._upgrade
        if upgrade is None:
            return None
        notes = upgrade.get("release_notes")
        return notes if isinstance(notes, str) else None

    @property
    def release_url(self) -> str | None:
        upgrade = self._upgrade
        if upgrade is None:
            return None
        url = upgrade.get("release_url")
        return url if isinstance(url, str) else None
