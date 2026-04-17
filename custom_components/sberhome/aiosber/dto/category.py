"""DeviceCategoryDto — категория устройства.

Wire: элемент массива ``full_categories`` в DeviceDto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class DeviceCategoryDto:
    """Категория устройства (wire: ``full_categories`` array element)."""

    id: str | None = None
    name: str | None = None
    slug: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["DeviceCategoryDto"]
