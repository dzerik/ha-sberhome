"""Support for SberHome binary sensors — sbermap-driven (PR #3 рефакторинга).

Платформа полностью обслуживается через `coordinator.entities`.
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.BINARY_SENSOR:
                entities.append(SberSbermapBinarySensor(coordinator, device_id, ent))
    # Sber-wide "at_home" — глобальная переменная, читаемая через
    # /scenario/v2/home/variable/at_home. Прикрепляется к virtual
    # device-group "Sber Scenarios" (тот же что для scenario buttons).
    entities.append(SberAtHomeBinarySensor(coordinator))
    async_add_entities(entities)


class SberSbermapBinarySensor(SberBaseEntity, BinarySensorEntity):
    """Universal binary sensor driven by sbermap HaEntityData."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        ha_entity: HaEntityData,
    ) -> None:
        dto = coordinator.devices.get(device_id)
        device_real_id = (dto.id if dto else None) or device_id
        prefix = f"{device_real_id}_"
        suffix = (
            ha_entity.unique_id[len(prefix) :] if ha_entity.unique_id.startswith(prefix) else ""
        )
        super().__init__(coordinator, device_id, suffix)
        self._ha_unique_id = ha_entity.unique_id
        self._attr_device_class = ha_entity.device_class
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category
        if not ha_entity.enabled_by_default:
            self._attr_entity_registry_enabled_default = False
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon

    @property
    def is_on(self) -> bool | None:
        ent = self._entity_data(self._ha_unique_id)
        if ent is None:
            return None
        # state хранится как "on"/"off"/None из STATE_ON/STATE_OFF.
        if ent.state == "on":
            return True
        if ent.state == "off":
            return False
        return None


class SberAtHomeBinarySensor(CoordinatorEntity[SberHomeCoordinator], BinarySensorEntity):
    """Read-only mirror Sber-переменной at_home (присутствие в доме).

    Запись доступна через `switch.sber_at_home` (см. switch.py) — он
    шлёт `set_at_home` через ScenarioAPI. Sensor нужен для использования
    в HA-автоматизациях как trigger / condition с понятной семантикой
    `binary_sensor` device_class=presence.
    """

    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:home-account"
    _attr_name = "At home"
    _attr_unique_id = "sberhome_at_home_sensor"

    def __init__(self, coordinator: SberHomeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    @property
    def available(self) -> bool:
        # None — переменная не настроена (никто не сетил at_home в Sber);
        # show entity but unavailable, не валим сами.
        return self.coordinator.at_home is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.at_home
