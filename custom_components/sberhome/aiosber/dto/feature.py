"""DeviceFeatureDto — описание constraints/ranges атрибутов устройства.

Wire: поле ``attributes`` в DeviceDto (массив объектов).
Каждый DeviceFeatureDto описывает один атрибут: ключ, тип, допустимые
диапазоны значений (int/float/string/enum/color/schedule) и видимость.

Источник: wire-анализ протокола Sber Gateway.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .enums import AttributeValueType

# ---------------------------------------------------------------------------
# Nested range / values types
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class IntRange:
    """Integer range constraint: min/max/step."""

    min: int = 0
    max: int = 0
    step: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class FloatRange:
    """Float range constraint: min/max."""

    min: float = 0.0
    max: float = 0.0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class ColorRange:
    """Color channel range constraint: min/max/step (for h/s/v)."""

    min: int = 0
    max: int = 0
    step: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


# ---------------------------------------------------------------------------
# Value constraint containers
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class IntValues:
    """Integer attribute constraints."""

    range: IntRange | None = None
    unit: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class FloatValues:
    """Float attribute constraints."""

    range: FloatRange | None = None
    unit: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class StringValues:
    """String attribute constraints."""

    max_length: int | None = None
    regex: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        # Wire uses camelCase: maxLength
        if isinstance(data, dict) and "maxLength" in data and "max_length" not in data:
            data = {**data, "max_length": data["maxLength"]}
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class EnumValues:
    """Enum attribute constraints: list of allowed string values."""

    values: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class ColorValues:
    """Color attribute constraints: h/s/v ranges."""

    h: ColorRange | None = None
    s: ColorRange | None = None
    v: ColorRange | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class ScheduleValues:
    """Schedule attribute marker (no additional constraints in wire)."""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return cls()

    def to_dict(self) -> dict[str, Any]:
        return {}


# ---------------------------------------------------------------------------
# Main DTO
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class DeviceFeatureDto:
    """Описание одного атрибута устройства с constraints/ranges.

    Wire: элемент массива ``attributes`` в DeviceDto.
    """

    key: str | None = None
    type: AttributeValueType | None = None
    name: str | None = None
    is_visible: bool | None = None
    int_values: IntValues | None = None
    float_values: FloatValues | None = None
    string_values: StringValues | None = None
    enum_values: EnumValues | None = None
    color_values: ColorValues | None = None
    schedule_values: ScheduleValues | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = [
    "ColorRange",
    "ColorValues",
    "DeviceFeatureDto",
    "EnumValues",
    "FloatRange",
    "FloatValues",
    "IntRange",
    "IntValues",
    "ScheduleValues",
    "StringValues",
]
