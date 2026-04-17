"""Тесты ColorValue, ScheduleValue, AttributeValueDto."""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto import (
    AttributeValueDto,
    AttributeValueType,
    AttrKey,
    ColorValue,
    ScheduleDay,
    ScheduleValue,
)


# ============== ColorValue ==============
def test_color_value_field_names():
    """Поля HSV — hue/saturation/brightness, НЕ h/s/v."""
    c = ColorValue(hue=120, saturation=100, brightness=80)
    d = c.to_dict()
    assert d == {"hue": 120, "saturation": 100, "brightness": 80}
    assert "h" not in d and "s" not in d and "v" not in d


def test_color_value_roundtrip():
    src = {"hue": 0, "saturation": 100, "brightness": 50}
    c = ColorValue.from_dict(src)
    assert c == ColorValue(0, 100, 50)
    assert c.to_dict() == src


def test_color_value_zero_values_serialized():
    """ColorValue не пропускает нули (omit_none=False) — нужно для valid commands."""
    c = ColorValue(0, 0, 0)
    assert c.to_dict() == {"hue": 0, "saturation": 0, "brightness": 0}


# ============== ScheduleValue ==============
def test_schedule_value_roundtrip():
    src = {
        "days": ["monday", "tuesday", "wednesday"],
        "events": [
            {"time": "08:00", "value_type": "FLOAT", "target_value": 22.5},
            {"time": "22:00", "value_type": "FLOAT", "target_value": 18.0},
        ],
    }
    sv = ScheduleValue.from_dict(src)
    assert sv.days == [ScheduleDay.MONDAY, ScheduleDay.TUESDAY, ScheduleDay.WEDNESDAY]
    assert len(sv.events) == 2
    assert sv.events[0].time == "08:00"
    assert sv.events[0].value_type is AttributeValueType.FLOAT
    assert sv.events[0].target_value == 22.5
    # roundtrip
    assert sv.to_dict() == src


# ============== AttributeValueDto ==============
def test_av_bool():
    av = AttributeValueDto.of_bool(AttrKey.ON_OFF, True)
    assert av.to_dict() == {"key": "on_off", "type": "BOOL", "bool_value": True}
    assert av.value is True


def test_av_int():
    av = AttributeValueDto.of_int(AttrKey.LIGHT_BRIGHTNESS, 500)
    assert av.to_dict() == {
        "key": "light_brightness",
        "type": "INTEGER",
        "integer_value": 500,
    }
    assert av.value == 500


def test_av_float():
    av = AttributeValueDto.of_float(AttrKey.TEMPERATURE, 23.5)
    assert av.to_dict() == {"key": "temperature", "type": "FLOAT", "float_value": 23.5}
    assert av.value == 23.5


def test_av_enum():
    av = AttributeValueDto.of_enum(AttrKey.HVAC_WORK_MODE, "cool")
    assert av.to_dict() == {
        "key": "hvac_work_mode",
        "type": "ENUM",
        "enum_value": "cool",
    }
    assert av.value == "cool"


def test_av_color():
    av = AttributeValueDto.of_color(
        AttrKey.LIGHT_COLOUR, ColorValue(hue=240, saturation=90, brightness=70)
    )
    assert av.to_dict() == {
        "key": "light_colour",
        "type": "COLOR",
        "color_value": {"hue": 240, "saturation": 90, "brightness": 70},
    }
    assert av.value == ColorValue(240, 90, 70)


def test_av_omits_none_fields():
    """to_dict() пропускает все None поля (короткий payload)."""
    av = AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=False)
    d = av.to_dict()
    assert "string_value" not in d
    assert "integer_value" not in d
    assert "color_value" not in d
    assert d["bool_value"] is False  # False НЕ должен пропадать


def test_av_from_dict_with_color():
    src = {
        "key": "light_colour",
        "type": "COLOR",
        "color_value": {"hue": 0, "saturation": 100, "brightness": 100},
        "last_sync": "2026-04-15T12:00:00.000Z",
    }
    av = AttributeValueDto.from_dict(src)
    assert av.type is AttributeValueType.COLOR
    assert av.color_value == ColorValue(0, 100, 100)
    assert av.last_sync == "2026-04-15T12:00:00.000Z"


def test_av_value_property_returns_active_field():
    """`.value` смотрит на type и возвращает соответствующее *_value."""
    cases = [
        (AttributeValueDto(type=AttributeValueType.BOOL, bool_value=True), True),
        (AttributeValueDto(type=AttributeValueType.INTEGER, integer_value=42), 42),
        (AttributeValueDto(type=AttributeValueType.STRING, string_value="x"), "x"),
        (AttributeValueDto(type=AttributeValueType.ENUM, enum_value="auto"), "auto"),
    ]
    for av, expected in cases:
        assert av.value == expected


def test_av_unknown_keys_ignored_on_parse():
    """Неизвестные поля в JSON не ломают from_dict."""
    src = {"key": "x", "type": "BOOL", "bool_value": True, "unknown_field": "ignore_me"}
    av = AttributeValueDto.from_dict(src)
    assert av.bool_value is True


def test_av_integer_value_from_string():
    """Wire-формат: integer_value приходит как строка — конвертируем в int."""
    src = {"key": "light_brightness", "type": "INTEGER", "integer_value": "500"}
    av = AttributeValueDto.from_dict(src)
    assert av.integer_value == 500
    assert isinstance(av.integer_value, int)


def test_av_integer_value_from_int():
    """integer_value как int — без изменений."""
    src = {"key": "light_brightness", "type": "INTEGER", "integer_value": 500}
    av = AttributeValueDto.from_dict(src)
    assert av.integer_value == 500


def test_av_integer_value_from_zero_string():
    """integer_value "0" — корректно конвертируется."""
    src = {"key": "x", "type": "INTEGER", "integer_value": "0"}
    av = AttributeValueDto.from_dict(src)
    assert av.integer_value == 0
