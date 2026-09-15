"""Команды лампы: build_light_command и чтение диапазонов из device.attributes.

Устройство — лампа с «родными» диапазонами Beken cb2l (яркость и S/V 1..1000),
в форме реального ответа `/devices`. Ожидаемые числа считаются штатными
преобразованиями HA (`brightness_to_value`, `scale_ranged_value_to_int_range`) —
тесты проверяют, какие атрибуты и в каких диапазонах уходят в Sber.
"""

from __future__ import annotations

import math

from homeassistant.util.color import brightness_to_value
from homeassistant.util.scaling import scale_ranged_value_to_int_range

from custom_components.sberhome.aiosber.dto import AttributeValueDto, DeviceDto
from custom_components.sberhome.sbermap.transform.lights import (
    H_RANGE,
    S_RANGE,
    build_light_command,
    light_config_from_dto,
)

_CB2L_ATTRIBUTES = [
    {"key": "on_off", "type": "BOOL"},
    {
        "key": "light_brightness",
        "type": "INTEGER",
        "int_values": {"range": {"min": 1, "max": 1000}},
    },
    {
        "key": "light_colour_temp",
        "type": "INTEGER",
        "int_values": {"range": {"min": 0, "max": 1000}},
    },
    {"key": "light_mode", "type": "ENUM", "enum_values": {"values": ["white", "colour", "scene"]}},
    {"key": "light_scene", "type": "ENUM", "enum_values": {"values": ["candle", "party"]}},
    {
        "key": "light_colour",
        "type": "COLOR",
        "color_values": {
            "h": {"min": 0, "max": 360, "step": 1},
            "s": {"min": 0, "max": 1000, "step": 1},
            "v": {"min": 1, "max": 1000, "step": 1},
        },
    },
]


def _dto(attributes: list[dict], image_set_type: str = "dt_bulb_e27_m") -> DeviceDto:
    dto = DeviceDto.from_dict(
        {"id": "lamp-1", "image_set_type": image_set_type, "attributes": attributes}
    )
    assert dto is not None
    return dto


CONFIG = light_config_from_dto(_dto(_CB2L_ATTRIBUTES))


def _by_key(attrs: list[AttributeValueDto]) -> dict[str, AttributeValueDto]:
    return {a.key: a for a in attrs}


def _v(ha_brightness: int) -> int:
    return math.ceil(brightness_to_value(CONFIG.color_v_range, ha_brightness))


def test_config_reads_native_ranges_and_options():
    assert CONFIG.brightness_range == (1, 1000)
    assert CONFIG.color_s_range == (0, 1000)
    assert CONFIG.color_v_range == (1, 1000)
    assert CONFIG.has_brightness and CONFIG.has_color_temp and CONFIG.has_colour
    assert CONFIG.light_modes == ("white", "colour", "scene")
    assert CONFIG.scene_options == ("candle", "party")


def test_config_without_full_colour_description_disables_colour():
    no_values = _dto([{"key": "light_colour", "type": "COLOR"}])
    missing_v = _dto(
        [
            {
                "key": "light_colour",
                "type": "COLOR",
                "color_values": {"h": {"min": 0, "max": 360}, "s": {"min": 0, "max": 100}},
            }
        ]
    )
    enum_without_values = _dto([{"key": "light_mode", "type": "ENUM"}])
    for dto in (no_values, missing_v):
        config = light_config_from_dto(dto)
        assert config.has_colour is False
        assert config.color_v_range == (1, 100)
    assert light_config_from_dto(enum_without_values).light_modes == ()


def test_colour_change_keeps_current_brightness_and_switches_mode():
    """Смена цвета без яркости не сбрасывает лампу на 100%."""
    attrs = build_light_command(
        CONFIG,
        "lamp-1",
        is_on=True,
        hs_color=(120.0, 50.0),
        current_state={"brightness": 128, "light_mode": "white"},
    )
    by_key = _by_key(attrs)
    assert [a.key for a in attrs] == ["on_off", "light_mode", "light_colour"]
    assert by_key["light_mode"].enum_value == "colour"
    colour = by_key["light_colour"].color_value
    assert colour.hue == scale_ranged_value_to_int_range(H_RANGE, CONFIG.color_h_range, 120.0)
    assert colour.saturation == scale_ranged_value_to_int_range(S_RANGE, CONFIG.color_s_range, 50.0)
    assert colour.brightness == _v(128)


def test_colour_with_brightness_in_colour_mode_skips_light_mode():
    """Повторный light_mode на прошивке cb2l обнуляет цвет — в colour mode его не шлём."""
    attrs = build_light_command(
        CONFIG,
        "lamp-1",
        is_on=True,
        brightness=64,
        hs_color=(0.0, 100.0),
        current_state={"brightness": 200, "light_mode": "colour"},
    )
    assert [a.key for a in attrs] == ["on_off", "light_colour", "light_brightness"]
    by_key = _by_key(attrs)
    assert by_key["light_colour"].color_value.brightness == _v(64)
    assert by_key["light_brightness"].integer_value == math.ceil(
        brightness_to_value(CONFIG.brightness_range, 64)
    )


def test_colour_without_any_known_brightness_uses_full():
    attrs = build_light_command(CONFIG, "lamp-1", is_on=True, hs_color=(240.0, 100.0))
    assert _by_key(attrs)["light_colour"].color_value.brightness == _v(255)


def test_colour_temperature_with_brightness():
    attrs = build_light_command(
        CONFIG, "lamp-1", is_on=True, brightness=255, color_temp_kelvin=4600
    )
    assert [a.key for a in attrs] == [
        "on_off",
        "light_mode",
        "light_colour_temp",
        "light_brightness",
    ]
    by_key = _by_key(attrs)
    assert by_key["light_mode"].enum_value == "white"
    assert by_key["light_colour_temp"].integer_value == scale_ranged_value_to_int_range(
        CONFIG.real_color_temp_range, CONFIG.color_temp_range, 4600
    )
    assert by_key["light_brightness"].integer_value == 1000


def test_white_mode_brightness():
    attrs = build_light_command(CONFIG, "lamp-1", is_on=True, white=200)
    by_key = _by_key(attrs)
    assert by_key["light_mode"].enum_value == "white"
    assert by_key["light_brightness"].integer_value == math.ceil(
        brightness_to_value(CONFIG.brightness_range, 200)
    )


def test_brightness_only_in_colour_mode_updates_v_and_keeps_hue():
    """В colour mode Sber игнорирует light_brightness — яркость едет в V цвета."""
    attrs = build_light_command(
        CONFIG,
        "lamp-1",
        is_on=True,
        brightness=100,
        current_state={"light_mode": "colour", "hs_color": (30.0, 80.0), "brightness": 255},
    )
    assert [a.key for a in attrs] == ["on_off", "light_mode", "light_colour"]
    colour = _by_key(attrs)["light_colour"].color_value
    assert colour.hue == scale_ranged_value_to_int_range(H_RANGE, CONFIG.color_h_range, 30.0)
    assert colour.brightness == _v(100)


def test_brightness_only_in_colour_mode_without_known_hue_uses_red_origin():
    attrs = build_light_command(
        CONFIG, "lamp-1", is_on=True, brightness=100, current_state={"light_mode": "colour"}
    )
    colour = _by_key(attrs)["light_colour"].color_value
    assert colour.hue == scale_ranged_value_to_int_range(H_RANGE, CONFIG.color_h_range, 0.0)
    assert colour.saturation == scale_ranged_value_to_int_range(S_RANGE, CONFIG.color_s_range, 0.0)


def test_config_tolerates_enum_with_null_values():
    """ENUM с `"enum_values": {"values": null}` — пустые режимы, а не TypeError.

    DTO-слой сохраняет такой ответ как `EnumValues(values=None)`; сбой здесь
    ронял бы создание всех ламп платформы.
    """
    dto = _dto(
        [
            {
                "key": "light_brightness",
                "type": "INTEGER",
                "int_values": {"range": {"min": 100, "max": 900}},
            },
            {"key": "light_mode", "type": "ENUM", "enum_values": {"values": None}},
            {"key": "light_scene", "type": "ENUM", "enum_values": {"values": None}},
        ]
    )
    config = light_config_from_dto(dto)
    assert config.light_modes == ()
    assert config.scene_options == ()
    assert config.brightness_range == (100, 900)
    assert config.has_brightness is True


def test_config_skips_null_attribute_elements():
    """`null` в `attributes[]` пропускается, остальные описания читаются."""
    dto = _dto(
        [
            None,  # type: ignore[list-item]
            {
                "key": "light_brightness",
                "type": "INTEGER",
                "int_values": {"range": {"min": 1, "max": 100}},
            },
            None,  # type: ignore[list-item]
            {"key": "light_mode", "type": "ENUM", "enum_values": {"values": ["white", "colour"]}},
            {
                "key": "light_colour",
                "type": "COLOR",
                "color_values": {
                    "h": {"min": 0, "max": 360},
                    "s": {"min": 0, "max": 100},
                    "v": {"min": 1, "max": 100},
                },
            },
        ]
    )
    config = light_config_from_dto(dto)
    assert config.brightness_range == (1, 100)
    assert config.has_brightness is True
    assert config.light_modes == ("white", "colour")
    assert config.has_colour is True
    assert config.has_color_temp is False
