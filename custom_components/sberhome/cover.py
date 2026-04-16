"""Support for SberHome covers — sbermap-driven (PR #5 + bidirectional PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
    CoverState,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import (
    HaEntityData,
    build_cover_position_command,
    build_cover_stop_command,
    cover_config_for,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapCover] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.COVER:
                entities.append(SberSbermapCover(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapCover(SberBaseEntity, CoverEntity):
    """Universal cover — read через coordinator.entities, write через bundle."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        ha_entity: HaEntityData,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._ha_unique_id = ha_entity.unique_id
        if ha_entity.device_class is not None:
            self._attr_device_class = ha_entity.device_class
        category = ha_entity.sber_category or ""
        config = cover_config_for(category)
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if config.supports_set_position:
            features |= CoverEntityFeature.SET_POSITION
        if config.supports_stop:
            features |= CoverEntityFeature.STOP
        self._attr_supported_features = features

    def _ent(self) -> HaEntityData | None:
        return self._entity_data(self._ha_unique_id)

    @property
    def current_cover_position(self) -> int | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.attributes.get("current_position")

    @property
    def is_closed(self) -> bool | None:
        ent = self._ent()
        if ent is None:
            return None
        if ent.state == CoverState.CLOSED:
            return True
        if ent.state in (CoverState.OPEN, CoverState.OPENING, CoverState.CLOSING):
            return False
        return None

    @property
    def is_opening(self) -> bool | None:
        ent = self._ent()
        return ent is not None and ent.state == CoverState.OPENING

    @property
    def is_closing(self) -> bool | None:
        ent = self._ent()
        return ent is not None and ent.state == CoverState.CLOSING

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._async_send_bundle(
            build_cover_position_command(device_id=self._device_id, position=100)
        )

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._async_send_bundle(
            build_cover_position_command(device_id=self._device_id, position=0)
        )

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._async_send_bundle(
            build_cover_position_command(
                device_id=self._device_id, position=kwargs[ATTR_POSITION]
            )
        )

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._async_send_bundle(
            build_cover_stop_command(device_id=self._device_id)
        )
