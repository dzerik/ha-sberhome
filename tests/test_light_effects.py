"""Tests for light effects integration (v5.4.0)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
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


def test_current_effect_resolved_from_state():
    """Когда light_mode=scene и light_scene=<id>, .effect возвращает name."""
    dto = DeviceDto(
        id="dev-1",
        image_set_type="cat_bulb_m",
        attributes=[
            DeviceFeatureDto(
                key="light_mode",
                enum_values=EnumValues(values=["white", "scene"]),
            ),
        ],
        full_categories=None,
        reported_state=[
            AttributeValueDto(key="light_mode", type=AttributeValueType.ENUM, enum_value="scene"),
            AttributeValueDto(
                key="light_scene", type=AttributeValueType.STRING, string_value="rainbow"
            ),
            AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True),
        ],
    )
    coord = _coord_with_dto(dto, effects=[{"id": "rainbow", "name": "Радуга"}])
    light = SberLightEntity(coord, "dev-1")
    assert light.effect == "Радуга"


@pytest.mark.asyncio
async def test_turn_on_with_effect_sends_correct_attrs():
    """light.turn_on(effect="Радуга") → light_mode=scene + light_scene=rainbow + on_off=true."""
    dto = DeviceDto(
        id="dev-1",
        image_set_type="cat_bulb_m",
        attributes=[
            DeviceFeatureDto(
                key="light_mode",
                enum_values=EnumValues(values=["white", "scene"]),
            ),
        ],
        full_categories=None,
        reported_state=[],
    )
    coord = _coord_with_dto(dto, effects=[{"id": "rainbow", "name": "Радуга"}])
    coord.async_send_device_state = AsyncMock()
    light = SberLightEntity(coord, "dev-1")

    await light.async_turn_on(effect="Радуга")

    coord.async_send_device_state.assert_awaited_once()
    args = coord.async_send_device_state.await_args.args
    assert args[0] == "dev-1"
    sent_attrs = args[1]
    sent_dict = {a.key: a for a in sent_attrs}
    assert sent_dict["light_mode"].enum_value == "scene"
    assert sent_dict["light_scene"].string_value == "rainbow"
    assert sent_dict["on_off"].bool_value is True


@pytest.mark.asyncio
async def test_unknown_effect_name_falls_back_to_plain_on(caplog):
    """light.turn_on(effect="Неизвестно") логирует warning, делает plain on."""
    dto = DeviceDto(
        id="dev-1",
        image_set_type="cat_bulb_m",
        attributes=[
            DeviceFeatureDto(
                key="light_mode",
                enum_values=EnumValues(values=["white", "scene"]),
            ),
        ],
        full_categories=None,
        reported_state=[],
    )
    coord = _coord_with_dto(dto, effects=[{"id": "rainbow", "name": "Радуга"}])
    coord.async_send_device_state = AsyncMock()
    light = SberLightEntity(coord, "dev-1")

    with caplog.at_level("WARNING"):
        await light.async_turn_on(effect="Несуществующий эффект")

    args = coord.async_send_device_state.await_args.args
    sent_dict = {a.key: a for a in args[1]}
    assert "light_scene" not in sent_dict
    assert any("Несуществующий" in rec.message for rec in caplog.records)


def test_effect_none_when_lightmode_not_scene():
    """Если light_mode != scene, .effect возвращает None."""
    dto = DeviceDto(
        id="dev-1",
        image_set_type="cat_bulb_m",
        attributes=[
            DeviceFeatureDto(
                key="light_mode",
                enum_values=EnumValues(values=["white", "scene"]),
            ),
        ],
        full_categories=None,
        reported_state=[
            AttributeValueDto(key="light_mode", type=AttributeValueType.ENUM, enum_value="white"),
            AttributeValueDto(
                key="light_scene", type=AttributeValueType.STRING, string_value="rainbow"
            ),
        ],
    )
    coord = _coord_with_dto(dto, effects=[{"id": "rainbow", "name": "Радуга"}])
    light = SberLightEntity(coord, "dev-1")
    assert light.effect is None
