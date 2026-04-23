"""Support for SberHome humidifiers — sbermap-driven (PR #6 + bidirectional PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.humidifier import (
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import (
    HaEntityData,
    build_humidifier_on_off_command,
    build_humidifier_set_humidity_command,
    build_humidifier_set_mode_command,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapHumidifier] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.HUMIDIFIER:
                entities.append(SberSbermapHumidifier(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapHumidifier(SberBaseEntity, HumidifierEntity):
    """Universal humidifier — modes/min_humidity/max_humidity из HaEntityData."""

    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        ha_entity: HaEntityData,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._ha_unique_id = ha_entity.unique_id
        if ha_entity.min_value is not None:
            self._attr_min_humidity = int(ha_entity.min_value)
        if ha_entity.max_value is not None:
            self._attr_max_humidity = int(ha_entity.max_value)
        features = HumidifierEntityFeature(0)
        if ha_entity.options:
            features |= HumidifierEntityFeature.MODES
            self._attr_available_modes = list(ha_entity.options)
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
    def target_humidity(self) -> int | None:
        ent = self._ent()
        if ent is None:
            return None
        h = ent.attributes.get("humidity")
        return int(h) if h is not None else None

    @property
    def mode(self) -> str | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.attributes.get("mode")

    async def async_set_humidity(self, humidity: int) -> None:
        await self._async_send_attrs(
            build_humidifier_set_humidity_command(device_id=self._device_id, humidity=humidity)
        )

    async def async_set_mode(self, mode: str) -> None:
        await self._async_send_attrs(
            build_humidifier_set_mode_command(device_id=self._device_id, mode=mode)
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_humidifier_on_off_command(device_id=self._device_id, is_on=True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_humidifier_on_off_command(device_id=self._device_id, is_on=False)
        )
