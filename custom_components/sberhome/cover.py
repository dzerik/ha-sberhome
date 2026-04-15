"""Support for SberHome covers (curtain, gate, window_blind, valve)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.cover import (
    ATTR_POSITION,
    CoverEntity,
    CoverEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_COVERS, CoverSpec, resolve_category


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericCover] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        spec = CATEGORY_COVERS.get(category)
        if spec is not None:
            entities.append(SberGenericCover(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericCover(SberBaseEntity, CoverEntity):
    """Универсальный cover по sber spec."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: CoverSpec,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._spec = spec
        if spec.device_class:
            self._attr_device_class = spec.device_class
        features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE
        if spec.supports_set_position:
            features |= CoverEntityFeature.SET_POSITION
        if spec.supports_stop:
            features |= CoverEntityFeature.STOP
        self._attr_supported_features = features

    @property
    def current_cover_position(self) -> int | None:
        """Позиция 0 (закрыто) — 100 (открыто). В Sber так же."""
        state = self._get_reported_state(self._spec.position_key)
        if state and "integer_value" in state:
            return int(state["integer_value"])
        return None

    @property
    def is_closed(self) -> bool | None:
        state = self._get_reported_state(self._spec.state_key)
        if state and "enum_value" in state:
            return state["enum_value"] == "closed"
        pos = self.current_cover_position
        if pos is not None:
            return pos == 0
        return None

    @property
    def is_opening(self) -> bool | None:
        state = self._get_reported_state(self._spec.state_key)
        if state and "enum_value" in state:
            return state["enum_value"] == "opening"
        return None

    @property
    def is_closing(self) -> bool | None:
        state = self._get_reported_state(self._spec.state_key)
        if state and "enum_value" in state:
            return state["enum_value"] == "closing"
        return None

    async def _send_position(self, position: int) -> None:
        await self._async_send_states(
            [{"key": self._spec.set_key, "integer_value": int(position)}]
        )

    async def async_open_cover(self, **kwargs: Any) -> None:
        await self._send_position(100)

    async def async_close_cover(self, **kwargs: Any) -> None:
        await self._send_position(0)

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        await self._send_position(kwargs[ATTR_POSITION])

    async def async_stop_cover(self, **kwargs: Any) -> None:
        await self._async_send_states(
            [{"key": self._spec.state_key, "enum_value": "stop"}]
        )
