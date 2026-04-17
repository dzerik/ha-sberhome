"""Support for SberHome fans — sbermap-driven (PR #6 + bidirectional PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import (
    HaEntityData,
    build_fan_preset_command,
    build_fan_turn_off_command,
    build_fan_turn_on_command,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapFan] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.FAN:
                entities.append(SberSbermapFan(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapFan(SberBaseEntity, FanEntity):
    """Universal fan — preset_mode mapped from sbermap.HaEntityData.options."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        ha_entity: HaEntityData,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._ha_unique_id = ha_entity.unique_id
        features = FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        if ha_entity.options:
            features |= FanEntityFeature.PRESET_MODE
            self._attr_preset_modes = list(ha_entity.options)
        self._attr_supported_features = features

    def _ent(self) -> HaEntityData | None:
        return self._entity_data(self._ha_unique_id)

    @property
    def is_on(self) -> bool | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.state == "on"

    @property
    def preset_mode(self) -> str | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.attributes.get("preset_mode")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._async_send_attrs(
            build_fan_preset_command(
                device_id=self._device_id, preset_mode=preset_mode
            )
        )

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        await self._async_send_attrs(
            build_fan_turn_on_command(
                device_id=self._device_id, preset_mode=preset_mode
            )
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_fan_turn_off_command(device_id=self._device_id)
        )
