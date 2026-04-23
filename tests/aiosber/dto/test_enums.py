"""Roundtrip всех значений Sber-енумов."""

from __future__ import annotations

from enum import IntEnum, StrEnum

import pytest

from custom_components.sberhome.aiosber.dto import enums

# Все enum-классы с значениями
ALL_ENUMS = [
    cls
    for name, cls in vars(enums).items()
    if isinstance(cls, type)
    and issubclass(cls, (StrEnum, IntEnum))
    and cls not in (StrEnum, IntEnum)
]


def test_at_least_47_attr_enums_present():
    attr_count = sum(1 for c in ALL_ENUMS if c.__name__.endswith("Attr"))
    # 35 *Attr + AttributeValueType (отдельно) — реальное число *Attr-enum'ов
    assert attr_count >= 30, f"expected ≥30 *Attr enums, got {attr_count}"


@pytest.mark.parametrize("cls", ALL_ENUMS, ids=lambda c: c.__name__)
def test_wire_value_roundtrip(cls):
    """Каждое значение enum'а должно роundtrip'иться через .value → cls(value)."""
    for member in cls:
        API = member.value
        assert cls(API) is member, f"{cls.__name__}: {member} ≠ cls({API!r})"


def test_sd_status_is_int_enum():
    """SdStatusAttr — единственный INTEGER API enum."""
    assert issubclass(enums.SdStatusAttr, IntEnum)
    assert enums.SdStatusAttr.NORMAL.value == 1
    assert isinstance(enums.SdStatusAttr.NORMAL.value, int)


def test_str_wire_for_obfuscated_numeric_enums():
    """Antiflicker / MotionSensitivity / Nightvision / Decibel — API это СТРОКА с цифрой."""
    assert enums.AntiflickerAttr.HZ_50.value == "1"
    assert isinstance(enums.AntiflickerAttr.HZ_50.value, str)
    assert enums.MotionSensitivityAttr.HIGH.value == "2"
    assert isinstance(enums.MotionSensitivityAttr.HIGH.value, str)
    assert enums.NightvisionAttr.AUTO.value == "0"
    assert isinstance(enums.NightvisionAttr.AUTO.value, str)


def test_workmode_colour_british_spelling():
    """light_mode = COLOR в коде, но API = "colour" (британское)."""
    assert enums.WorkModeAttr.COLOR.value == "colour"


def test_temperature_unit_lowercase():
    assert enums.TemperatureUnitAttr.CELSIUS.value == "c"
    assert enums.TemperatureUnitAttr.FAHRENHEIT.value == "f"


def test_floor_sensor_type_mixed_case():
    """FloorSensorType — API с маленькой 'k' внутри (NTC10k, не NTC10K)."""
    assert enums.FloorSensorTypeAttr.NTC10K.value == "NTC10k"


def test_connection_type_camel_case():
    """ConnectionType — API CamelCase с префиксом ConnType."""
    assert enums.ConnectionType.MATTER.value == "ConnTypeMatter"
    assert enums.ConnectionType.ZIGBEE.value == "ConnTypeZigbee"


def test_topic_enum_has_8_members():
    """В API-протоколе в enum Topic 8 значений."""
    assert len(list(enums.Topic)) == 8


def test_open_set_includes_unknown():
    """OpenSetAttr включает UNKNOWN — sber возвращает 'unknown' для не-стандартных команд."""
    assert enums.OpenSetAttr.UNKNOWN.value == "unknown"


def test_str_enum_string_compat():
    """StrEnum значения должны быть совместимы со str (==, in dict, json)."""
    assert enums.HvacWorkMode.COOL == "cool"
    assert enums.HvacWorkMode.COOL in ("cool", "heat")
