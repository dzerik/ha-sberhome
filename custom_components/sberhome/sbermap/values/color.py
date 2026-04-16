"""Canonical HSV color model — codec-agnostic.

Wire-форматы Sber API используют разные шкалы:
- Gateway: `{hue: 0..359, saturation: 0..100, brightness: 0..100}`.
- C2C:     `{h: 0..360, s: 0..1000, v: 100..1000}`.

`HsvColor` — единая каноническая модель в **percentage scale** (0..100 для
saturation/brightness, 0..359 для hue). Codec'и преобразуют в/из wire.

Это позволяет HA-side код работать с одной типизированной моделью, не зная о
расхождениях между протоколами.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class HsvColor:
    """HSV цвет в canonical scale.

    Args:
        hue: 0..359 (degrees).
        saturation: 0..100 (percent).
        brightness: 0..100 (percent).

    Validation: значения **clamped** в свои диапазоны (вместо raise — это
    обёртки над user-input от HA, где могут быть граничные значения).
    """

    hue: int = 0
    saturation: int = 0
    brightness: int = 0

    def __post_init__(self) -> None:
        # Frozen dataclass — обходим через object.__setattr__.
        object.__setattr__(self, "hue", _clamp(self.hue, 0, 359))
        object.__setattr__(self, "saturation", _clamp(self.saturation, 0, 100))
        object.__setattr__(self, "brightness", _clamp(self.brightness, 0, 100))

    @classmethod
    def from_ha(cls, h: float, s: float, brightness: int | None = None) -> HsvColor:
        """Сконструировать из HA-формата (hs_color = (hue 0-360, sat 0-100), brightness 0-255)."""
        b = round(brightness * 100 / 255) if brightness is not None else 100
        return cls(hue=int(round(h)), saturation=int(round(s)), brightness=b)

    def to_ha_hs(self) -> tuple[float, float]:
        """Вернуть `(hue, saturation)` в HA-формате (для ATTR_HS_COLOR)."""
        return (float(self.hue), float(self.saturation))

    def to_ha_brightness(self) -> int:
        """Вернуть brightness в HA-формате 0..255."""
        return round(self.brightness * 255 / 100)


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, int(value)))
