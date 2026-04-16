"""Support for SberHome lights — sbermap-driven (PR #4 рефакторинга).

Вся scaling-логика (HSV ranges, color_temp Kelvin↔Sber, brightness 100..900)
живёт в `sbermap.transform.lights`. Платформа лишь оркеструет: читает state
через `light_state_from_dto`, пишет через `build_light_command` →
`_async_send_bundle`.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_HS_COLOR,
    ATTR_WHITE,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import (
    LightConfig,
    build_light_command,
    light_config_from_dto,
    light_state_from_dto,
    resolve_category,
)

_LIGHT_CATEGORIES = {"light", "led_strip"}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberLightEntity] = []
    for device_id, dto in coordinator.devices.items():
        category = resolve_category(dto.image_set_type)
        if category not in _LIGHT_CATEGORIES:
            continue
        entities.append(SberLightEntity(coordinator, device_id))
    async_add_entities(entities)


class SberLightEntity(SberBaseEntity, LightEntity):
    """SberHome light — read/write через sbermap.transform.lights."""

    def __init__(
        self, coordinator: SberHomeCoordinator, device_id: str
    ) -> None:
        super().__init__(coordinator, device_id)
        # Config извлекается один раз — он зависит от device.attributes
        # (которые от refresh к refresh обычно не меняются).
        self._config: LightConfig = self._compute_config()

    def _compute_config(self) -> LightConfig:
        dto = self._device_dto
        return light_config_from_dto(dto) if dto is not None else LightConfig()

    def _state(self) -> dict[str, Any]:
        dto = self._device_dto
        if dto is None:
            return {}
        return light_state_from_dto(dto, self._config)

    @property
    def is_on(self) -> bool | None:
        return self._state().get("is_on")

    @property
    def brightness(self) -> int | None:
        return self._state().get("brightness")

    @property
    def hs_color(self) -> tuple[float, float] | None:
        if ColorMode.HS not in self.supported_color_modes:
            return None
        return self._state().get("hs_color")

    @property
    def color_temp_kelvin(self) -> int | None:
        if ColorMode.COLOR_TEMP not in self.supported_color_modes:
            return None
        return self._state().get("color_temp_kelvin")

    @property
    def min_color_temp_kelvin(self) -> int:
        return self._config.real_color_temp_range[0]

    @property
    def max_color_temp_kelvin(self) -> int:
        return self._config.real_color_temp_range[1]

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        modes: set[ColorMode] = set()
        cfg = self._config
        if cfg.has_colour and "colour" in cfg.light_modes:
            modes.add(ColorMode.HS)
        if "white" in cfg.light_modes:
            if cfg.has_color_temp:
                modes.add(ColorMode.COLOR_TEMP)
            elif cfg.has_brightness:
                modes.add(ColorMode.BRIGHTNESS)
        if not modes and cfg.has_brightness:
            modes.add(ColorMode.BRIGHTNESS)
        return modes or {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        light_mode = self._state().get("light_mode")
        if light_mode == "white":
            if ColorMode.COLOR_TEMP in self.supported_color_modes:
                return ColorMode.COLOR_TEMP
            return ColorMode.BRIGHTNESS
        if light_mode == "colour":
            return ColorMode.HS
        return ColorMode.UNKNOWN

    async def async_turn_on(self, **kwargs: Any) -> None:
        bundle = build_light_command(
            self._config,
            self._device_id,
            is_on=True,
            brightness=kwargs.get(ATTR_BRIGHTNESS),
            hs_color=kwargs.get(ATTR_HS_COLOR),
            color_temp_kelvin=kwargs.get(ATTR_COLOR_TEMP_KELVIN),
            white=kwargs.get(ATTR_WHITE),
        )
        await self._async_send_bundle(bundle)

    async def async_turn_off(self, **kwargs: Any) -> None:
        bundle = build_light_command(self._config, self._device_id, is_on=False)
        await self._async_send_bundle(bundle)
