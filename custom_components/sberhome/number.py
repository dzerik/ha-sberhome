"""Support for SberHome number entities (e.g. kettle target temp, sleep timer)."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_NUMBERS, NumberSpec, resolve_category


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericNumber] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        for spec in CATEGORY_NUMBERS.get(category, []):
            entities.append(SberGenericNumber(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericNumber(SberBaseEntity, NumberEntity):
    """Универсальный числовой слайдер/ввод через NumberSpec."""

    _attr_mode = NumberMode.AUTO

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: NumberSpec,
    ) -> None:
        super().__init__(coordinator, device_id, spec.suffix)
        self._spec = spec
        if spec.unit:
            self._attr_native_unit_of_measurement = spec.unit
        if spec.min_value is not None:
            self._attr_native_min_value = spec.min_value
        if spec.max_value is not None:
            self._attr_native_max_value = spec.max_value
        if spec.step is not None:
            self._attr_native_step = spec.step
        if spec.entity_category is not None:
            self._attr_entity_category = spec.entity_category
        if spec.icon is not None:
            self._attr_icon = spec.icon

    @property
    def native_value(self) -> float | None:
        state = self._get_desired_state(self._spec.key)
        if not state:
            return None
        if "integer_value" in state:
            return float(state["integer_value"]) * self._spec.scale
        if "float_value" in state:
            return state["float_value"] * self._spec.scale
        return None

    async def async_set_native_value(self, value: float) -> None:
        raw = int(value / self._spec.scale) if self._spec.scale else int(value)
        await self._async_send_states(
            [{"key": self._spec.key, "integer_value": raw}]
        )
