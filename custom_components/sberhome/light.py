"""Support for SberHome lights."""

from __future__ import annotations

import math
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
from homeassistant.util.color import brightness_to_value, value_to_brightness
from homeassistant.util.scaling import scale_ranged_value_to_int_range

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import resolve_category

_LIGHT_CATEGORIES = {"light", "led_strip"}


def _get_color_temp_kelvin_range(device_type: str) -> tuple[int, int]:
    match device_type:
        case "ledstrip":
            return 2000, 6500
        case _:
            return 2700, 6500


H_RANGE = (0, 360)
S_RANGE = (0, 100)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberLightEntity] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category not in _LIGHT_CATEGORIES:
            continue
        # led_strip имеет шире диапазон color temp; для обычного bulb — стандартный.
        device_type = "ledstrip" if category == "led_strip" else "bulb"
        entities.append(SberLightEntity(coordinator, device_id, device_type))
    async_add_entities(entities)


class SberLightEntity(SberBaseEntity, LightEntity):
    """Representation of a SberHome light."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        device_type: str,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._hs_color: tuple[float, float] | None = None
        self._real_color_temp_range = _get_color_temp_kelvin_range(device_type)

    @property
    def is_on(self) -> bool | None:
        state = self._get_desired_state("on_off")
        if state is None or "bool_value" not in state:
            return None
        return state["bool_value"]

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        modes: set[ColorMode] = set()
        light_mode = self._get_attribute("light_mode")
        if light_mode:
            values = light_mode["enum_values"]["values"]
            if "colour" in values:
                modes.add(ColorMode.HS)
            if "white" in values:
                if self._get_attribute("light_colour_temp") is not None:
                    modes.add(ColorMode.COLOR_TEMP)
                elif self._get_attribute("light_brightness") is not None:
                    modes.add(ColorMode.BRIGHTNESS)
        if not modes and self._get_attribute("light_brightness") is not None:
            modes.add(ColorMode.BRIGHTNESS)
        return modes or {ColorMode.ONOFF}

    @property
    def color_mode(self) -> ColorMode:
        state = self._get_desired_state("light_mode")
        if state:
            match state["enum_value"]:
                case "white":
                    if ColorMode.COLOR_TEMP in self.supported_color_modes:
                        return ColorMode.COLOR_TEMP
                    return ColorMode.BRIGHTNESS
                case "colour":
                    return ColorMode.HS
        return ColorMode.UNKNOWN

    @property
    def _brightness_range(self) -> tuple[int, int]:
        attr = self._get_attribute("light_brightness")
        if attr:
            r = attr["int_values"]["range"]
            return (r["min"], r["max"])
        return (1, 255)

    @property
    def brightness(self) -> int | None:
        if self.color_mode == ColorMode.HS:
            state = self._get_desired_state("light_colour")
            if state and "color_value" in state:
                return value_to_brightness(
                    self._color_range["v"], state["color_value"]["v"]
                )

        state = self._get_desired_state("light_brightness")
        if state:
            return value_to_brightness(
                self._brightness_range, int(state["integer_value"])
            )
        return None

    @property
    def min_color_temp_kelvin(self) -> int:
        return self._real_color_temp_range[0]

    @property
    def max_color_temp_kelvin(self) -> int:
        return self._real_color_temp_range[1]

    @property
    def _color_temp_range(self) -> tuple[int, int]:
        attr = self._get_attribute("light_colour_temp")
        if attr:
            r = attr["int_values"]["range"]
            return (r["min"], r["max"])
        return (0, 100)

    @property
    def color_temp_kelvin(self) -> int | None:
        if ColorMode.COLOR_TEMP not in self.supported_color_modes:
            return None
        state = self._get_desired_state("light_colour_temp")
        if state:
            return scale_ranged_value_to_int_range(
                self._color_temp_range,
                self._real_color_temp_range,
                int(state["integer_value"]),
            )
        return None

    @property
    def _color_range(self) -> dict[str, tuple[int, int]]:
        attr = self._get_attribute("light_colour")
        if attr:
            cv = attr["color_values"]
            return {
                "h": (cv["h"]["min"], cv["h"]["max"]),
                "s": (cv["s"]["min"], cv["s"]["max"]),
                "v": (cv["v"]["min"], cv["v"]["max"]),
            }
        return {"h": (0, 360), "s": (0, 100), "v": (1, 100)}

    @property
    def hs_color(self) -> tuple[float, float] | None:
        if ColorMode.HS not in self.supported_color_modes:
            return None
        if self._hs_color is not None:
            return self._hs_color
        state = self._get_desired_state("light_colour")
        if state and "color_value" in state:
            colour = state["color_value"]
            return (
                scale_ranged_value_to_int_range(
                    self._color_range["h"], H_RANGE, colour["h"]
                ),
                scale_ranged_value_to_int_range(
                    self._color_range["s"], S_RANGE, colour["s"]
                ),
            )
        return None

    def _handle_coordinator_update(self) -> None:
        """Reset cached HS color when coordinator updates."""
        self._hs_color = None
        super()._handle_coordinator_update()

    # --- State builders ---

    def _brightness_state(self, brightness: int) -> dict:
        """Build light_brightness state dict."""
        return {
            "key": "light_brightness",
            "integer_value": math.ceil(
                brightness_to_value(self._brightness_range, brightness)
            ),
        }

    def _colour_state(self, h: float, s: float, brightness: int) -> dict:
        """Build light_colour state dict with HSV values."""
        return {
            "key": "light_colour",
            "color_value": {
                "h": scale_ranged_value_to_int_range(
                    H_RANGE, self._color_range["h"], h
                ),
                "s": scale_ranged_value_to_int_range(
                    S_RANGE, self._color_range["s"], s
                ),
                "v": math.ceil(
                    brightness_to_value(self._color_range["v"], brightness)
                ),
            },
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        states: list[dict] = [{"key": "on_off", "bool_value": True}]

        hs_color = kwargs.get(ATTR_HS_COLOR)
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        color_temp = kwargs.get(ATTR_COLOR_TEMP_KELVIN)
        white = kwargs.get(ATTR_WHITE)

        if hs_color is not None:
            h, s = hs_color
            self._hs_color = (h, s)
            current_brightness = self.brightness or 255
            states.append({"key": "light_mode", "enum_value": "colour"})
            states.append(
                self._colour_state(h, s, brightness or current_brightness)
            )
            if brightness is not None:
                states.append(self._brightness_state(brightness))

        elif color_temp is not None:
            t = scale_ranged_value_to_int_range(
                self._real_color_temp_range,
                self._color_temp_range,
                color_temp,
            )
            states.append({"key": "light_mode", "enum_value": "white"})
            states.append({"key": "light_colour_temp", "integer_value": max(0, t)})
            if brightness is not None:
                states.append(self._brightness_state(brightness))

        elif white is not None:
            states.append({"key": "light_mode", "enum_value": "white"})
            states.append(self._brightness_state(white))

        elif brightness is not None:
            if self.color_mode == ColorMode.HS:
                color = self.hs_color or (0, 0)
                states.append({"key": "light_mode", "enum_value": "colour"})
                states.append(self._brightness_state(brightness))
                states.append(self._colour_state(color[0], color[1], brightness))
            else:
                states.append({"key": "light_mode", "enum_value": "white"})
                states.append(self._brightness_state(brightness))

        await self.coordinator.home_api.set_device_state(
            self._device_id, states
        )
        self.coordinator.async_set_updated_data(
            self.coordinator.home_api.get_cached_devices()
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.home_api.set_device_state(
            self._device_id, [{"key": "on_off", "bool_value": False}]
        )
        self.coordinator.async_set_updated_data(
            self.coordinator.home_api.get_cached_devices()
        )
