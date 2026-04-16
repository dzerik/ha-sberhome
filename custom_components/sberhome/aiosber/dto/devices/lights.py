"""Lights — `light` и `led_strip`."""

from __future__ import annotations

from ..values import ColorValue
from ._base import TypedDevice


class LightDevice(TypedDevice):
    """Умная лампа.

    spec features: on_off, online, light_brightness (100-900), light_colour (HSV),
    light_colour_temp, light_mode (white/colour/...).
    """

    CATEGORIES = ("light",)

    @property
    def is_on(self) -> bool | None:
        return self._reported_bool("on_off")

    @property
    def brightness(self) -> int | None:
        """Raw яркость (100-900). HA-mapping масштабирует на 0-255."""
        return self._reported_int("light_brightness")

    @property
    def color(self) -> ColorValue | None:
        """HSV цвет."""
        attr = self._dto.reported("light_colour")
        return attr.color_value if attr else None

    @property
    def color_temp(self) -> int | None:
        return self._reported_int("light_colour_temp")

    @property
    def mode(self) -> str | None:
        """`white` / `colour` / `adaptive` / `scene` / `music`."""
        return self._reported_str("light_mode")


class LedStripDevice(LightDevice):
    """LED-лента — все фичи `light` + sleep_timer."""

    CATEGORIES = ("led_strip",)

    @property
    def sleep_timer(self) -> int | None:
        """Минут до автоматического выключения (0 = выключен)."""
        return self._reported_int("sleep_timer")
