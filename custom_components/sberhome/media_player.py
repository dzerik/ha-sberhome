"""Support for SberHome TVs — sbermap-driven (PR #7 + PR #9)."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import (
    TV_SOURCES,
    HaEntityData,
    build_tv_channel_command,
    build_tv_custom_key_command,
    build_tv_direction_command,
    build_tv_mute_command,
    build_tv_on_off_command,
    build_tv_source_command,
    build_tv_volume_command,
    build_tv_volume_step_command,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapMediaPlayer] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.MEDIA_PLAYER:
                entities.append(SberSbermapMediaPlayer(coordinator, device_id, ent))
    async_add_entities(entities)

    try:
        platform = entity_platform.async_get_current_platform()
    except RuntimeError:
        return
    platform.async_register_entity_service(
        "send_custom_key",
        {vol.Required("key"): vol.In(["confirm", "back", "home"])},
        "async_send_custom_key",
    )
    platform.async_register_entity_service(
        "send_direction",
        {vol.Required("direction"): vol.In(["up", "down", "left", "right"])},
        "async_send_direction",
    )
    platform.async_register_entity_service(
        "play_channel",
        {vol.Required("channel"): vol.Coerce(int)},
        "async_play_channel",
    )


class SberSbermapMediaPlayer(SberBaseEntity, MediaPlayerEntity):
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
        ha_entity: HaEntityData,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._ha_unique_id = ha_entity.unique_id
        self._attr_source_list = list(TV_SOURCES)

    def _ent(self) -> HaEntityData | None:
        return self._entity_data(self._ha_unique_id)

    @property
    def state(self) -> MediaPlayerState:
        ent = self._ent()
        if ent is None:
            return MediaPlayerState.OFF
        return MediaPlayerState.ON if ent.state == "on" else MediaPlayerState.OFF

    @property
    def volume_level(self) -> float | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.attributes.get("volume_level")

    @property
    def is_volume_muted(self) -> bool | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.attributes.get("is_volume_muted")

    @property
    def source(self) -> str | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.attributes.get("source")

    async def async_turn_on(self) -> None:
        await self._async_send_bundle(
            build_tv_on_off_command(device_id=self._device_id, is_on=True)
        )

    async def async_turn_off(self) -> None:
        await self._async_send_bundle(
            build_tv_on_off_command(device_id=self._device_id, is_on=False)
        )

    async def async_set_volume_level(self, volume: float) -> None:
        await self._async_send_bundle(
            build_tv_volume_command(
                device_id=self._device_id, volume_level=volume
            )
        )

    async def async_volume_up(self) -> None:
        await self._async_send_bundle(
            build_tv_volume_step_command(
                device_id=self._device_id, direction="+"
            )
        )

    async def async_volume_down(self) -> None:
        await self._async_send_bundle(
            build_tv_volume_step_command(
                device_id=self._device_id, direction="-"
            )
        )

    async def async_mute_volume(self, mute: bool) -> None:
        await self._async_send_bundle(
            build_tv_mute_command(device_id=self._device_id, mute=mute)
        )

    async def async_select_source(self, source: str) -> None:
        await self._async_send_bundle(
            build_tv_source_command(device_id=self._device_id, source=source)
        )

    async def async_send_custom_key(self, key: str) -> None:
        await self._async_send_bundle(
            build_tv_custom_key_command(device_id=self._device_id, key=key)
        )

    async def async_send_direction(self, direction: str) -> None:
        await self._async_send_bundle(
            build_tv_direction_command(
                device_id=self._device_id, direction=direction
            )
        )

    async def async_play_channel(self, channel: int) -> None:
        await self._async_send_bundle(
            build_tv_channel_command(
                device_id=self._device_id, channel=channel
            )
        )
