"""Support for SberHome fans (hvac_fan, hvac_air_purifier)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_FANS, FanSpec, resolve_category


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericFan] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        spec = CATEGORY_FANS.get(category)
        if spec is not None:
            entities.append(SberGenericFan(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericFan(SberBaseEntity, FanEntity):
    """Универсальный вентилятор."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: FanSpec,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._spec = spec
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if spec.speed_key and spec.speeds:
            features |= FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = list(spec.speeds)
        self._attr_supported_features = features

    @property
    def is_on(self) -> bool | None:
        state = self._get_desired_state("on_off")
        return bool(state and state.get("bool_value"))

    @property
    def preset_mode(self) -> str | None:
        if not self._spec.speed_key:
            return None
        state = self._get_desired_state(self._spec.speed_key)
        return state["enum_value"] if state and "enum_value" in state else None

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        if not self._spec.speed_key:
            return
        await self._async_send_states(
            [{"key": self._spec.speed_key, "enum_value": preset_mode}]
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        states: list[dict] = [{"key": "on_off", "bool_value": True}]
        if preset_mode and self._spec.speed_key:
            states.append({"key": self._spec.speed_key, "enum_value": preset_mode})
        await self._async_send_states(states)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_states([{"key": "on_off", "bool_value": False}])
