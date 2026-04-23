"""Regression tests for sbermap.transform.lights — real-world device payloads.

Особенно важно: `dt_bulb_e27_m` (Sber 2025+ формат) приходит с ВСЕМИ
value-полями заполненными дефолтами — `bool_value: false`,
`integer_value: "0"`, `enum_value: ""`, но без `color_value` для
`light_colour` атрибута. Наивный "первое не-None" возвращал
`bool_value=False` как color, и `light_state_from_dto` падал с
`AttributeError: 'bool' object has no attribute 'hue'`.
"""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.sbermap.transform.lights import (
    light_config_from_dto,
    light_state_from_dto,
)


def _make_dt_bulb_e27_m() -> dict:
    """Реальный payload `dt_bulb_e27_m` — образец от пользователя на проде.

    Ключевые особенности:
    - `light_colour` с type=COLOR, color_value отсутствует, но bool_value=false.
    - `light_mode` ENUM = "music" (в desired_state).
    - `light_brightness` INTEGER = 50.
    """
    return {
        "id": "cgsausn56600c5uid640",
        "name": {"name": "Лампа 1"},
        "image_set_type": "dt_bulb_e27_m",
        "sw_version": "1.32.14",
        "serial_number": "A8805513E919",
        "device_info": {"manufacturer": "Sber", "model": "SBDV-00115"},
        "attributes": [
            {
                "key": "light_brightness",
                "int_values": {"range": {"min": 1, "max": 1000}},
            },
            {
                "key": "light_colour_temp",
                "int_values": {"range": {"min": 0, "max": 100}},
            },
            {
                "key": "light_mode",
                "enum_values": {"values": ["white", "colour", "music"]},
            },
            {
                "key": "light_colour",
                "color_values": {
                    "h": {"min": 0, "max": 360},
                    "s": {"min": 0, "max": 100},
                    "v": {"min": 1, "max": 100},
                },
            },
        ],
        "reported_state": [
            {"key": "on_off", "type": "BOOL", "bool_value": True},
            {"key": "light_brightness", "type": "INTEGER", "integer_value": "1000"},
            {"key": "light_mode", "type": "ENUM", "enum_value": "white"},
            # light_colour с bool_value: false — НЕТ color_value.
            # Это реальный Sber API payload: наивный первый-non-None
            # возвращал bool=False и падал в light_state_from_dto.
            {
                "key": "light_colour",
                "type": "COLOR",
                "bool_value": False,
                "integer_value": "0",
                "float_value": 0,
                "string_value": "",
                "enum_value": "",
            },
            # signal_strength — ENUM "low", НЕ INTEGER. Раньше `int("low")`
            # крашил весь coordinator refresh.
            {"key": "signal_strength", "type": "ENUM", "enum_value": "low"},
            {"key": "signal_strength_dbm", "type": "INTEGER", "integer_value": "-100"},
        ],
        "desired_state": [
            {"key": "on_off", "type": "BOOL", "bool_value": True},
            {"key": "light_brightness", "type": "INTEGER", "integer_value": "50"},
            {"key": "light_mode", "type": "ENUM", "enum_value": "music"},
            {
                "key": "light_colour",
                "type": "COLOR",
                "bool_value": False,
                "integer_value": "0",
                "float_value": 0,
                "string_value": "",
                "enum_value": "",
            },
        ],
    }


def test_light_state_from_dto_handles_empty_color_value() -> None:
    """`light_colour` с type=COLOR но без color_value — light_state не падает.

    Раньше возвращался `bool_value=False` вместо None, и при попытке
    `color_obj.hue` падал AttributeError.
    """
    dto = DeviceDto.from_dict(_make_dt_bulb_e27_m())
    assert dto is not None

    config = light_config_from_dto(dto)
    state = light_state_from_dto(dto, config)

    # Не падает, возвращает валидный view
    assert state["is_on"] is True
    # brightness из light_brightness (music mode → но color_obj None, fallback на brightness_raw)
    assert state["brightness"] is not None
    # hs_color должен быть None — color_value отсутствует
    assert state["hs_color"] is None
    # light_mode из desired_state
    assert state["light_mode"] == "music"


def test_map_device_to_entities_survives_type_mismatch() -> None:
    """Regression: раньше `signal_strength` был IntegerCodec, но реальные
    dt_bulb_e27_m присылают его как ENUM ("low"/"medium"/"high"). При
    `int("low")` crashил весь coordinator refresh — интеграция теряла ВСЕ
    устройства. Теперь `signal_strength` → EnumCodec, `signal_strength_dbm` →
    IntegerCodec, плюс `IntegerCodec.to_ha` возвращает None вместо raise
    при любом type mismatch."""
    from custom_components.sberhome.sbermap import map_device_to_entities

    dto = DeviceDto.from_dict(_make_dt_bulb_e27_m())
    assert dto is not None

    # Не падает
    entities = map_device_to_entities(dto)
    assert isinstance(entities, list)
    # signal_strength entity есть (как ENUM sensor)
    ss_entities = [e for e in entities if e.unique_id.endswith("_signal_strength")]
    assert len(ss_entities) == 1
    assert ss_entities[0].state == "low"  # ENUM value как есть


def test_light_state_from_dto_respects_type_field() -> None:
    """Проверяем что _desired_value использует av.value (type-aware), не
    fallback на первое не-None value-поле."""
    payload = _make_dt_bulb_e27_m()
    dto = DeviceDto.from_dict(payload)
    assert dto is not None

    # light_colour должно давать None (color_value отсутствует в DTO),
    # а НЕ bool_value=False.
    from custom_components.sberhome.sbermap.transform.lights import _desired_value

    assert _desired_value(dto, "light_colour") is None
    # light_brightness должен дать integer value (тип INTEGER) = "50".
    assert _desired_value(dto, "light_brightness") == "50"
    # light_mode должен дать enum value.
    assert _desired_value(dto, "light_mode") == "music"
    # on_off — BOOL.
    assert _desired_value(dto, "on_off") is True
