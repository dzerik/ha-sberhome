"""Support for SberHome humidifiers (hvac_humidifier)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import (
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_HUMIDIFIERS, HumidifierSpec, resolve_category


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericHumidifier] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        spec = CATEGORY_HUMIDIFIERS.get(category)
        if spec is not None:
            entities.append(SberGenericHumidifier(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericHumidifier(SberBaseEntity, HumidifierEntity):
    """Универсальный увлажнитель."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: HumidifierSpec,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._spec = spec
        self._attr_min_humidity = spec.min_humidity
        self._attr_max_humidity = spec.max_humidity
        features = HumidifierEntityFeature(0)
        if spec.modes:
            features |= HumidifierEntityFeature.MODES
            self._attr_available_modes = list(spec.modes)
        self._attr_supported_features = features

    @property
    def is_on(self) -> bool | None:
        state = self._get_desired_state("on_off")
        return bool(state and state.get("bool_value"))

    @property
    def target_humidity(self) -> int | None:
        if not self._spec.target_humidity_key:
            return None
        state = self._get_desired_state(self._spec.target_humidity_key)
        if state and "integer_value" in state:
            return int(state["integer_value"])
        return None

    @property
    def mode(self) -> str | None:
        if not self._spec.mode_key:
            return None
        state = self._get_desired_state(self._spec.mode_key)
        return state["enum_value"] if state and "enum_value" in state else None

    async def async_set_humidity(self, humidity: int) -> None:
        if not self._spec.target_humidity_key:
            return
        await self._async_send_states(
            [{"key": self._spec.target_humidity_key, "integer_value": int(humidity)}]
        )

    async def async_set_mode(self, mode: str) -> None:
        if not self._spec.mode_key:
            return
        await self._async_send_states([{"key": self._spec.mode_key, "enum_value": mode}])

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_send_states([{"key": "on_off", "bool_value": True}])

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_states([{"key": "on_off", "bool_value": False}])
