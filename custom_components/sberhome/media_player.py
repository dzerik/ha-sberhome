"""Support for SberHome TVs (media_player)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_MEDIA_PLAYERS, MediaPlayerSpec, resolve_category


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberTvEntity] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        spec = CATEGORY_MEDIA_PLAYERS.get(category)
        if spec is not None:
            entities.append(SberTvEntity(coordinator, device_id, spec))
    async_add_entities(entities)


class SberTvEntity(SberBaseEntity, MediaPlayerEntity):
    """Sber TV — media_player."""

    _attr_supported_features = (
        MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
        | MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.SELECT_SOURCE
    )

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: MediaPlayerSpec,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._spec = spec
        self._attr_source_list = list(spec.sources)

    # ---- power ----
    @property
    def state(self) -> MediaPlayerState:
        on = self._get_desired_state("on_off")
        return (
            MediaPlayerState.ON
            if on and on.get("bool_value")
            else MediaPlayerState.OFF
        )

    async def async_turn_on(self) -> None:
        await self._async_send_states([{"key": "on_off", "bool_value": True}])

    async def async_turn_off(self) -> None:
        await self._async_send_states([{"key": "on_off", "bool_value": False}])

    # ---- volume ----
    @property
    def volume_level(self) -> float | None:
        state = self._get_desired_state(self._spec.volume_key)
        if state and "integer_value" in state:
            return float(state["integer_value"]) / self._spec.volume_max
        return None

    async def async_set_volume_level(self, volume: float) -> None:
        raw = int(volume * self._spec.volume_max)
        await self._async_send_states([{"key": self._spec.volume_key, "integer_value": raw}])

    async def async_volume_up(self) -> None:
        await self._async_send_states([{"key": self._spec.direction_key, "enum_value": "+"}])

    async def async_volume_down(self) -> None:
        await self._async_send_states([{"key": self._spec.direction_key, "enum_value": "-"}])

    @property
    def is_volume_muted(self) -> bool | None:
        state = self._get_desired_state(self._spec.mute_key)
        return bool(state and state.get("bool_value"))

    async def async_mute_volume(self, mute: bool) -> None:
        await self._async_send_states([{"key": self._spec.mute_key, "bool_value": mute}])

    # ---- source ----
    @property
    def source(self) -> str | None:
        state = self._get_desired_state(self._spec.source_key)
        return state["enum_value"] if state and "enum_value" in state else None

    async def async_select_source(self, source: str) -> None:
        await self._async_send_states([{"key": self._spec.source_key, "enum_value": source}])
