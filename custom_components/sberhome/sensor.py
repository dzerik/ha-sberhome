"""Support for SberHome sensors — sbermap-driven (PR #3 рефакторинга).

Платформа полностью обслуживается через `coordinator.entities` —
готовый кэш `HaEntityData` из `sbermap`. Никакой ad-hoc логики:
все scaling/units/device_class определены в `sbermap.transform.sber_to_ha`.

Дополнительно добавляется `SberHubSubdeviceCount` для устройств-хабов
(определяются через `coordinator._hub_device_ids()`) — diagnostic sensor
со счётчиком связанных sub-устройств из `/devices/{id}/discovery`.
"""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, Platform
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
    entities: list[SensorEntity] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.SENSOR:
                entities.append(SberSbermapSensor(coordinator, device_id, ent))
    # Diagnostic: для каждого hub-устройства — sub-device counter из
    # discovery. Создаются всегда, даже если discovery ещё не успел
    # отработать; до первого poll отдают None (unavailable в HA UI).
    for device_id in coordinator._hub_device_ids():
        entities.append(SberHubSubdeviceCount(coordinator, device_id))
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
        dto = coordinator.devices.get(device_id)
        device_real_id = (dto.id if dto else None) or device_id
        prefix = f"{device_real_id}_"
        suffix = (
            ha_entity.unique_id[len(prefix) :] if ha_entity.unique_id.startswith(prefix) else ""
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
            self._attr_suggested_display_precision = ha_entity.suggested_display_precision
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


class SberHubSubdeviceCount(SberBaseEntity, SensorEntity):
    """Diagnostic counter — сколько sub-устройств видит хаб через discovery.

    Источник данных: `coordinator.discovery_info[device_id]` — dict из
    `/devices/{id}/discovery`. Sber возвращает разные shapes для разных
    типов хабов; здесь поддерживается несколько распространённых форм:
    список под ключом `devices`, под `sub_devices`, или просто `count`.
    Если ничего не распарсили — sensor показывает None (unavailable).
    """

    _attr_has_entity_name = True
    _attr_name = "Sub-device count"
    _attr_icon = "mdi:hubspot"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
    ) -> None:
        super().__init__(coordinator, device_id, "subdevice_count")

    @property
    def native_value(self) -> int | None:
        info = self.coordinator.discovery_info.get(self._device_id)
        if not isinstance(info, dict):
            return None
        for key in ("devices", "sub_devices", "children"):
            value = info.get(key)
            if isinstance(value, list):
                return len(value)
        if isinstance(info.get("count"), int):
            return info["count"]
        return None
