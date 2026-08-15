"""Support for SberHome number entities — sbermap-driven (PR #7 + PR #9)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, StarosSettingEntity, build_number_command
from .staros_settings_entity import SberStarosSettingBase


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.NUMBER:
                entities.append(SberSbermapNumber(coordinator, device_id, ent))
    # Настройки-слайдеры умных колонок Сбера (громкость подсказок и т.п.).
    for specs in coordinator.staros_settings_entities.values():
        for spec in specs:
            if spec.platform is Platform.NUMBER:
                entities.append(SberStarosSettingNumber(coordinator, spec))
    async_add_entities(entities)


class SberSbermapNumber(SberBaseEntity, NumberEntity):
    _attr_mode = NumberMode.AUTO

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
        self._state_key = ha_entity.state_attribute_key or ""
        self._scale = ha_entity.scale
        if ha_entity.unit_of_measurement is not None:
            self._attr_native_unit_of_measurement = ha_entity.unit_of_measurement
        if ha_entity.min_value is not None:
            self._attr_native_min_value = ha_entity.min_value
        if ha_entity.max_value is not None:
            self._attr_native_max_value = ha_entity.max_value
        if ha_entity.step is not None:
            self._attr_native_step = ha_entity.step
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon

    @property
    def native_value(self) -> float | None:
        ent = self._entity_data(self._ha_unique_id)
        if ent is None:
            return None
        return ent.state

    async def async_set_native_value(self, value: float) -> None:
        await self._async_send_attrs(
            build_number_command(
                device_id=self._device_id,
                key=self._state_key,
                value=value,
                scale=self._scale,
            )
        )


class SberStarosSettingNumber(SberStarosSettingBase, NumberEntity):
    """Настройка-слайдер умной колонки Сбера."""

    _attr_mode = NumberMode.AUTO

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        spec: StarosSettingEntity,
    ) -> None:
        super().__init__(coordinator, spec)
        if spec.min_value is not None:
            self._attr_native_min_value = spec.min_value
        if spec.max_value is not None:
            self._attr_native_max_value = spec.max_value
        if spec.step is not None:
            self._attr_native_step = spec.step
        if spec.unit is not None:
            self._attr_native_unit_of_measurement = spec.unit

    @property
    def native_value(self) -> float | None:
        spec = self._current()
        if spec is None or spec.state is None:
            return None
        return float(spec.state)

    async def async_set_native_value(self, value: float) -> None:
        await self._async_write(value)
