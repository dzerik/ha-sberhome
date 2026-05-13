"""Tests for light effects integration (v5.4.0)."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.components.light import LightEntityFeature

from custom_components.sberhome.aiosber.dto import (
    AttributeValueDto,
    AttributeValueType,
    DeviceDto,
    EnumValues,
)
from custom_components.sberhome.aiosber.dto.feature import DeviceFeatureDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.light import SberLightEntity


def _bulb_dto(*, modes: list[str], with_scene_feature: bool = True) -> DeviceDto:
    """Build DeviceDto для лампы с заданным enum-values у light_mode."""
    attributes: list[DeviceFeatureDto] = []
    if with_scene_feature:
        attributes = [
            DeviceFeatureDto(
                key="light_mode",
                enum_values=EnumValues(values=list(modes)),
            ),
        ]
    return DeviceDto(
        id="dev-1",
        image_set_type="cat_bulb_m",
        attributes=attributes,
        full_categories=None,
        reported_state=[
            AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True),
        ],
    )


def _coord_with_dto(dto: DeviceDto, *, effects: list[dict] | None = None) -> MagicMock:
    cache = StateCache()
    cache._devices = {dto.id: dto}
    cache.set_light_effects(effects or [])
    coord = MagicMock()
    coord.devices = {dto.id: dto}
    coord.state_cache = cache
    return coord


def test_effect_support_when_lightmode_has_scene():
    """Лампа с light_mode enum, содержащим 'scene', получает EFFECT feature."""
    coord = _coord_with_dto(
        _bulb_dto(modes=["white", "colour", "scene"]),
        effects=[{"id": "rainbow", "name": "Радуга"}],
    )
    light = SberLightEntity(coord, "dev-1")
    assert light.supported_features & LightEntityFeature.EFFECT
    assert light.effect_list == ["Радуга"]


def test_no_effect_support_for_simple_bulb():
    """Лампа БЕЗ 'scene' в light_mode enum — EFFECT не включается."""
    coord = _coord_with_dto(
        _bulb_dto(modes=["white", "colour"]),  # no 'scene'
        effects=[{"id": "rainbow", "name": "Радуга"}],
    )
    light = SberLightEntity(coord, "dev-1")
    assert not (light.supported_features & LightEntityFeature.EFFECT)
    assert light.effect_list is None


def test_empty_catalog_no_effect_list():
    """Лампа умеет scene, но каталог пустой — effect_list пустой list."""
    coord = _coord_with_dto(
        _bulb_dto(modes=["white", "scene"]),
        effects=[],
    )
    light = SberLightEntity(coord, "dev-1")
    assert light.supported_features & LightEntityFeature.EFFECT
    assert light.effect_list == []
