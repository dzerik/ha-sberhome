"""UnionDto, UnionTreeDto — группы, комнаты, дом.

Wire: ответ ``GET /device_groups/tree`` — рекурсивное дерево ``UnionTreeDto``.
Каждый node содержит ``union`` (метаданные группы, wire key ``"group"``),
``devices`` (устройства в этой группе), ``children`` (дочерние группы).

``UnionType``: NONE, GROUP, HOME, ROOM — тип группы.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .device import DeviceDto, ImagesDto, OwnerInfoDto


class UnionType(StrEnum):
    """Тип группы (wire: ``group_type``)."""

    NONE = "NONE"
    GROUP = "GROUP"
    HOME = "HOME"
    ROOM = "ROOM"


@dataclass(slots=True, frozen=True)
class UnionDto:
    """Группа/комната/дом.

    Wire: вложенный объект ``group`` внутри ``UnionTreeDto``.
    """

    id: str | None = None
    name: str | None = None
    parent_id: str | None = None
    group_type: UnionType | None = None
    device_ids: list[str] | None = None
    image_set_type: str | None = None
    images: ImagesDto | None = None
    owner_info: OwnerInfoDto | None = None
    sort_weight_int: int | None = None
    address: str | None = None
    # geoposition, settings, meta, address_details — dict для будущего
    settings: dict[str, Any] | None = None
    meta: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class UnionTreeDto:
    """Node дерева групп.

    Wire: ответ ``GET /device_groups/tree``. Рекурсивная структура.
    Wire key для метаданных группы — ``"group"`` (маппится в ``union``).
    """

    union: UnionDto | None = None
    devices: list[DeviceDto] = field(default_factory=list)
    children: list[UnionTreeDto] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        # Wire key "group" → наше поле "union"
        if isinstance(data, dict) and "group" in data and "union" not in data:
            data = {**data, "union": data["group"]}
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["UnionDto", "UnionTreeDto", "UnionType"]
