"""Value-types для AttributeValueDto: ColorValue, ScheduleValue, AttributeValueDto.

ColorValue использует поля `hue/saturation/brightness` — НЕ `h/s/v`.
Это критично: реверс APK подтверждает, что Sber Gateway ждёт именно эти имена.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .enums import AttributeValueType, ScheduleDay


@dataclass(slots=True, frozen=True)
class ColorValue:
    """HSV для AttributeValueDto.color_value.

    hue:        0..359
    saturation: 0..100
    brightness: 0..100
    """

    hue: int = 0
    saturation: int = 0
    brightness: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        # Поддержка двух форматов wire:
        # - canonical Sber: {hue, saturation, brightness}
        # - legacy наш: {h, s, v}
        if "h" in data and "hue" not in data:
            return cls(
                hue=int(data.get("h", 0)),
                saturation=int(data.get("s", 0)),
                brightness=int(data.get("v", 0)),
            )
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class ScheduleEvent:
    """Одно событие расписания."""

    time: str | None = None  # "HH:MM"
    value_type: AttributeValueType | None = None
    target_value: float | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class ScheduleValue:
    """Расписание (например для термостата / котла)."""

    days: list[ScheduleDay] = field(default_factory=list)
    events: list[ScheduleEvent] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class AttributeValueDto:
    """Универсальный контейнер значения атрибута.

    Заполнено только одно `*_value` поле, соответствующее `type`.
    Остальные — None (и не сериализуются благодаря omit_none).

    Примеры:

        AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True)

        AttributeValueDto(
            key="light_colour",
            type=AttributeValueType.COLOR,
            color_value=ColorValue(120, 100, 90),
        )

        AttributeValueDto(
            key="hvac_work_mode",
            type=AttributeValueType.ENUM,
            enum_value="cool",
        )
    """

    key: str | None = None
    type: AttributeValueType | None = None
    string_value: str | None = None
    integer_value: int | None = None
    float_value: float | None = None
    bool_value: bool | None = None
    enum_value: str | None = None
    color_value: ColorValue | None = None
    schedule_value: ScheduleValue | None = None
    last_sync: str | None = None

    # ----- удобные конструкторы -----
    @classmethod
    def of_bool(cls, key: str, value: bool) -> Self:
        return cls(key=key, type=AttributeValueType.BOOL, bool_value=value)

    @classmethod
    def of_int(cls, key: str, value: int) -> Self:
        return cls(key=key, type=AttributeValueType.INTEGER, integer_value=value)

    @classmethod
    def of_float(cls, key: str, value: float) -> Self:
        return cls(key=key, type=AttributeValueType.FLOAT, float_value=value)

    @classmethod
    def of_string(cls, key: str, value: str) -> Self:
        return cls(key=key, type=AttributeValueType.STRING, string_value=value)

    @classmethod
    def of_enum(cls, key: str, value: str) -> Self:
        return cls(key=key, type=AttributeValueType.ENUM, enum_value=value)

    @classmethod
    def of_color(cls, key: str, color: ColorValue) -> Self:
        return cls(key=key, type=AttributeValueType.COLOR, color_value=color)

    # ----- helpers -----
    @property
    def value(self) -> Any:
        """Вернуть актуальное значение в соответствии с type, без проверок."""
        if self.type is AttributeValueType.BOOL:
            return self.bool_value
        if self.type is AttributeValueType.INTEGER:
            return self.integer_value
        if self.type is AttributeValueType.FLOAT:
            return self.float_value
        if self.type is AttributeValueType.STRING:
            return self.string_value
        if self.type is AttributeValueType.ENUM:
            return self.enum_value
        if self.type is AttributeValueType.COLOR:
            return self.color_value
        if self.type is AttributeValueType.SCHEDULE:
            return self.schedule_value
        return None

    # ----- serialization -----
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)
