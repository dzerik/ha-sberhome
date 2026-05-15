"""Tests for light effects — сцены из light_scene enum устройства (v5.8.3)."""

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

# Реальные сцены SBDV-00055 (подтверждены на устройстве).
_SCENES = ["candle", "arctic", "romantic", "sunset", "dawn", "christmas", "fito"]


def _bulb_dto(
    *,
    modes: list[str],
    scenes: list[str] | None = None,
    reported: list[AttributeValueDto] | None = None,
) -> DeviceDto:
    """DeviceDto лампы с заданными light_mode и (опционально) light_scene enum."""
    attributes: list[DeviceFeatureDto] = [
        DeviceFeatureDto(key="light_mode", enum_values=EnumValues(values=list(modes))),
    ]
    if scenes is not None:
        attributes.append(
            DeviceFeatureDto(key="light_scene", enum_values=EnumValues(values=list(scenes)))
        )
    return DeviceDto(
        id="dev-1",
        image_set_type="cat_bulb_m",
        attributes=attributes,
        full_categories=None,
        reported_state=reported
        or [AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True)],
    )


def _coord_with_dto(dto: DeviceDto) -> MagicMock:
    cache = StateCache()
    cache.update_from_devices({dto.id: dto})
    coord = MagicMock()
    coord.devices = {dto.id: dto}
    coord.state_cache = cache
    return coord


def test_effect_support_when_lightmode_has_scene():
    """Лампа с 'scene' в light_mode enum + light_scene enum → EFFECT feature."""
    coord = _coord_with_dto(_bulb_dto(modes=["white", "colour", "scene"], scenes=_SCENES))
    light = SberLightEntity(coord, "dev-1")
    assert light.supported_features & LightEntityFeature.EFFECT
    assert light.effect_list == _SCENES


def test_no_effect_support_for_simple_bulb():
    """Лампа БЕЗ 'scene' в light_mode enum — EFFECT не включается."""
    coord = _coord_with_dto(_bulb_dto(modes=["white", "colour"], scenes=_SCENES))
    light = SberLightEntity(coord, "dev-1")
    assert not (light.supported_features & LightEntityFeature.EFFECT)
    assert light.effect_list is None


def test_effect_list_empty_when_no_light_scene_attr():
    """Лампа умеет scene-mode, но light_scene enum отсутствует — пустой список."""
    coord = _coord_with_dto(_bulb_dto(modes=["white", "scene"], scenes=None))
    light = SberLightEntity(coord, "dev-1")
    assert light.supported_features & LightEntityFeature.EFFECT
    assert light.effect_list == []


def test_current_effect_resolved_from_state():
    """light_mode=scene и light_scene=sunset → .effect возвращает 'sunset'."""
    dto = _bulb_dto(
        modes=["white", "scene"],
        scenes=_SCENES,
        reported=[
            AttributeValueDto(key="light_mode", type=AttributeValueType.ENUM, enum_value="scene"),
            AttributeValueDto(
                key="light_scene", type=AttributeValueType.ENUM, enum_value="sunset"
            ),
            AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True),
        ],
    )
    coord = _coord_with_dto(dto)
    light = SberLightEntity(coord, "dev-1")
    assert light.effect == "sunset"


def test_effect_none_when_lightmode_not_scene():
    """light_mode != scene → .effect возвращает None даже если light_scene задан."""
    dto = _bulb_dto(
        modes=["white", "scene"],
        scenes=_SCENES,
        reported=[
            AttributeValueDto(key="light_mode", type=AttributeValueType.ENUM, enum_value="white"),
            AttributeValueDto(
                key="light_scene", type=AttributeValueType.ENUM, enum_value="sunset"
            ),
        ],
    )
    coord = _coord_with_dto(dto)
    light = SberLightEntity(coord, "dev-1")
    assert light.effect is None


def test_effect_none_when_scene_unknown():
    """light_scene содержит значение вне enum → .effect возвращает None."""
    dto = _bulb_dto(
        modes=["white", "scene"],
        scenes=_SCENES,
        reported=[
            AttributeValueDto(key="light_mode", type=AttributeValueType.ENUM, enum_value="scene"),
            AttributeValueDto(
                key="light_scene", type=AttributeValueType.ENUM, enum_value="unknown_x"
            ),
        ],
    )
    coord = _coord_with_dto(dto)
    light = SberLightEntity(coord, "dev-1")
    assert light.effect is None


@pytest.mark.asyncio
async def test_turn_on_with_effect_sends_correct_attrs():
    """light.turn_on(effect='sunset') → light_mode=scene + light_scene=sunset + on_off=true."""
    coord = _coord_with_dto(_bulb_dto(modes=["white", "scene"], scenes=_SCENES))
    coord.async_send_device_state = AsyncMock()
    light = SberLightEntity(coord, "dev-1")

    await light.async_turn_on(effect="sunset")

    coord.async_send_device_state.assert_awaited_once()
    args = coord.async_send_device_state.await_args.args
    assert args[0] == "dev-1"
    sent = {a.key: a for a in args[1]}
    assert sent["light_mode"].enum_value == "scene"
    # light_scene — ENUM-атрибут: значение в enum_value, не string_value.
    assert sent["light_scene"].enum_value == "sunset"
    assert sent["light_scene"].type is AttributeValueType.ENUM
    assert sent["on_off"].bool_value is True


@pytest.mark.asyncio
async def test_unknown_effect_name_falls_back_to_plain_on(caplog):
    """light.turn_on(effect=<не из enum>) логирует warning и делает plain on."""
    coord = _coord_with_dto(_bulb_dto(modes=["white", "scene"], scenes=_SCENES))
    coord.async_send_device_state = AsyncMock()
    light = SberLightEntity(coord, "dev-1")

    with caplog.at_level("WARNING"):
        await light.async_turn_on(effect="Несуществующий эффект")

    coord.async_send_device_state.assert_awaited_once()
    args = coord.async_send_device_state.await_args.args
    sent = {a.key: a for a in args[1]}
    assert "light_scene" not in sent
    assert sent["on_off"].bool_value is True
    assert any("Несуществующий" in rec.message for rec in caplog.records)
