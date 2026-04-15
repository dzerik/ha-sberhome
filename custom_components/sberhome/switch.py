"""Support for SberHome switches (declarative via registry)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import (
    CATEGORY_EXTRA_SWITCHES,
    CATEGORY_SWITCHES,
    ExtraSwitchSpec,
    SwitchSpec,
    resolve_category,
)
from .utils import find_from_list


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericSwitch] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        spec = CATEGORY_SWITCHES.get(category)
        if spec is not None:
            entities.append(SberGenericSwitch(coordinator, device_id, spec))
        # Extra config switches (child_lock, night_mode) — только если есть в attributes.
        for extra in CATEGORY_EXTRA_SWITCHES.get(category, []):
            if _has_attribute(device, extra.key):
                entities.append(SberExtraSwitch(coordinator, device_id, extra))
    async_add_entities(entities)


def _has_attribute(device: dict, key: str) -> bool:
    if "attributes" not in device:
        return False
    return find_from_list(device["attributes"], key) is not None


class SberGenericSwitch(SberBaseEntity, SwitchEntity):
    """Универсальный switch через SwitchSpec."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: SwitchSpec,
    ) -> None:
        super().__init__(coordinator, device_id, spec.suffix)
        self._spec = spec

    @property
    def is_on(self) -> bool | None:
        state = self._get_desired_state(self._spec.key)
        if state is None or "bool_value" not in state:
            return None
        return state["bool_value"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_send_states(
            [{"key": self._spec.key, "bool_value": True}]
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_states(
            [{"key": self._spec.key, "bool_value": False}]
        )


class SberExtraSwitch(SberGenericSwitch):
    """Дополнительный toggle на устройстве (child_lock, night_mode)."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: ExtraSwitchSpec,
    ) -> None:
        # SwitchSpec с нужным ключом и суффиксом.
        sw = SwitchSpec(key=spec.key, suffix=spec.suffix)
        super().__init__(coordinator, device_id, sw)
        if spec.entity_category is not None:
            self._attr_entity_category = spec.entity_category
        if spec.icon is not None:
            self._attr_icon = spec.icon


class SberSwitchEntity(SberGenericSwitch):
    """Backwards-compat: default switch (socket on_off)."""

    def __init__(
        self, coordinator: SberHomeCoordinator, device_id: str
    ) -> None:
        super().__init__(coordinator, device_id, CATEGORY_SWITCHES["socket"])
