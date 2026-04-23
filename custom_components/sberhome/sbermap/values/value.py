"""Canonical SberValue — codec-agnostic tagged union.

Форматы данных Sber отличаются:
- Gateway: `{type: "BOOL", bool_value: true}`, INTEGER as int.
- C2C:     `{type: "BOOL", bool_value: true}`, INTEGER as **string**.
- Gateway: `type: "COLOR"`, C2C: `type: "COLOUR"`.

`SberValue` — единая модель. Codec'и (`gateway.py`/`c2c.py`) преобразуют
в/из серилизованный формат.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .color import HsvColor
from .schedule import ScheduleValue


class ValueType(StrEnum):
    """Канонический тип Sber value (codec-agnostic).

    Отображение в API:
    - `Codec.encode_value()` → `{"type": <wire_type>, "<wire_field>": ...}`.
    - `Codec.decode_value()` ← `<wire_type>` → ValueType.

    `COLOR` в Gateway, `COLOUR` в C2C — оба мапятся в `ValueType.COLOR`.
    """

    BOOL = "BOOL"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    STRING = "STRING"
    ENUM = "ENUM"
    COLOR = "COLOR"
    SCHEDULE = "SCHEDULE"


@dataclass(slots=True, frozen=True)
class SberValue:
    """Canonical typed value (codec-agnostic).

    Заполнено только одно поле, соответствующее `type`.
    """

    type: ValueType
    bool_value: bool | None = None
    integer_value: int | None = None
    float_value: float | None = None
    string_value: str | None = None
    enum_value: str | None = None
    color_value: HsvColor | None = None
    schedule_value: ScheduleValue | None = None

    @property
    def value(self) -> Any:
        """Вернуть актуальное value (без type-checking)."""
        if self.type is ValueType.BOOL:
            return self.bool_value
        if self.type is ValueType.INTEGER:
            return self.integer_value
        if self.type is ValueType.FLOAT:
            return self.float_value
        if self.type is ValueType.STRING:
            return self.string_value
        if self.type is ValueType.ENUM:
            return self.enum_value
        if self.type is ValueType.COLOR:
            return self.color_value
        if self.type is ValueType.SCHEDULE:
            return self.schedule_value
        return None

    # ---- Builders ----
    @classmethod
    def of_bool(cls, value: bool) -> SberValue:
        return cls(type=ValueType.BOOL, bool_value=value)

    @classmethod
    def of_int(cls, value: int) -> SberValue:
        return cls(type=ValueType.INTEGER, integer_value=int(value))

    @classmethod
    def of_float(cls, value: float) -> SberValue:
        return cls(type=ValueType.FLOAT, float_value=float(value))

    @classmethod
    def of_string(cls, value: str) -> SberValue:
        return cls(type=ValueType.STRING, string_value=str(value))

    @classmethod
    def of_enum(cls, value: str) -> SberValue:
        return cls(type=ValueType.ENUM, enum_value=value)

    @classmethod
    def of_color(cls, color: HsvColor) -> SberValue:
        return cls(type=ValueType.COLOR, color_value=color)

    @classmethod
    def of_schedule(cls, schedule: ScheduleValue) -> SberValue:
        return cls(type=ValueType.SCHEDULE, schedule_value=schedule)


@dataclass(slots=True, frozen=True)
class SberState:
    """One state entry: key + value."""

    key: str
    value: SberValue


@dataclass(slots=True, frozen=True)
class SberStateBundle:
    """Набор states для одного устройства."""

    device_id: str | None
    states: tuple[SberState, ...] = ()

    def get(self, key: str) -> SberValue | None:
        for s in self.states:
            if s.key == key:
                return s.value
        return None

    def value_of(self, key: str) -> Any:
        v = self.get(key)
        return v.value if v is not None else None
