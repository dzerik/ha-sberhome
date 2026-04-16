"""Support for SberHome sensors — sbermap-driven (PR #3 рефакторинга).

Платформа полностью обслуживается через `coordinator.entities` —
готовый кэш `HaEntityData` из `sbermap`. Никакой ad-hoc логики:
все scaling/units/device_class определены в `sbermap.transform.sber_to_ha`.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapSensor] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.SENSOR:
                entities.append(SberSbermapSensor(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapSensor(SberBaseEntity, SensorEntity):
    """Universal sensor driven by sbermap HaEntityData."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        ha_entity: HaEntityData,
    ) -> None:
        # unique_id-suffix вычисляем как часть после device_id_, иначе "" (primary).
        device_real_id = (
            coordinator.data[device_id].get("id") or device_id
            if device_id in coordinator.data
            else device_id
        )
        prefix = f"{device_real_id}_"
        suffix = (
            ha_entity.unique_id[len(prefix):]
            if ha_entity.unique_id.startswith(prefix)
            else ""
        )
        super().__init__(coordinator, device_id, suffix)
        # Запоминаем конкретный unique_id для lookup'а актуальной HaEntityData.
        self._ha_unique_id = ha_entity.unique_id
        self._attr_device_class = ha_entity.device_class
        self._attr_native_unit_of_measurement = ha_entity.unit_of_measurement
        self._attr_state_class = ha_entity.state_class
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category
        if ha_entity.suggested_display_precision is not None:
            self._attr_suggested_display_precision = (
                ha_entity.suggested_display_precision
            )
        if not ha_entity.enabled_by_default:
            self._attr_entity_registry_enabled_default = False
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon

    @property
    def native_value(self) -> float | int | str | None:
        """Каждый раз перечитываем актуальное HaEntityData из coordinator."""
        ent = self._entity_data(self._ha_unique_id)
        if ent is None:
            return None
        return ent.state
