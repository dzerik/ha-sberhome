"""Tests for SberLightEntity.supported_color_modes — HA color-mode validation.

Регрессия: лампа с режимами colour+white (has_colour, has_brightness, без
color_temp) отдавала {HS, BRIGHTNESS}, что HA отклоняет — BRIGHTNESS не может
соседствовать ни с каким другим цветовым режимом.
"""

from __future__ import annotations

import pytest
from homeassistant.components.light import ColorMode, valid_supported_color_modes

from custom_components.sberhome.light import SberLightEntity
from custom_components.sberhome.sbermap.transform.lights import LightConfig


def _modes_for(config: LightConfig) -> set[ColorMode]:
    """supported_color_modes — чистая функция от LightConfig (читает только _config)."""
    entity = object.__new__(SberLightEntity)
    entity._config = config
    return entity.supported_color_modes


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        # Регрессия: colour+white без color_temp — раньше {HS, BRIGHTNESS}.
        (
            LightConfig(
                has_colour=True,
                has_brightness=True,
                has_color_temp=False,
                light_modes=("colour", "white"),
            ),
            {ColorMode.HS},
        ),
        # colour+white с color_temp — два валидных цветовых режима.
        (
            LightConfig(
                has_colour=True,
                has_brightness=True,
                has_color_temp=True,
                light_modes=("colour", "white"),
            ),
            {ColorMode.HS, ColorMode.COLOR_TEMP},
        ),
        # Только white + яркость, без цвета — самостоятельный BRIGHTNESS.
        (
            LightConfig(has_brightness=True, light_modes=("white",)),
            {ColorMode.BRIGHTNESS},
        ),
        # Только colour.
        (
            LightConfig(has_colour=True, has_brightness=True, light_modes=("colour",)),
            {ColorMode.HS},
        ),
        # Лампа без яркости и цвета — ONOFF.
        (LightConfig(), {ColorMode.ONOFF}),
    ],
)
def test_supported_color_modes(config: LightConfig, expected: set[ColorMode]) -> None:
    modes = _modes_for(config)
    assert modes == expected
    # HA-валидатор не должен бросать — set всегда легитимен.
    valid_supported_color_modes(modes)
