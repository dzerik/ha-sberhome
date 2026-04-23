"""UnionDto, UnionTreeDto — группы, комнаты, дом.

JSON schema: ответ ``GET /device_groups/tree`` — рекурсивное дерево ``UnionTreeDto``.
Каждый node содержит ``union`` (метаданные группы, API key ``"group"``),
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
    """Тип группы (field key: ``group_type``)."""

    NONE = "NONE"
    GROUP = "GROUP"
    HOME = "HOME"
    ROOM = "ROOM"


@dataclass(slots=True, frozen=True)
class UnionDto:
    """Группа/комната/дом.

    JSON key: вложенный объект ``group`` внутри ``UnionTreeDto``.
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

    JSON key: ответ ``GET /device_groups/tree``. Рекурсивная структура.
    Field key для метаданных группы — ``"group"`` (маппится в ``union``).
    """

    union: UnionDto | None = None
    devices: list[DeviceDto] = field(default_factory=list)
    children: list[UnionTreeDto] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        if not isinstance(data, dict):
            return None
        # key "group" → наше поле "union"
        if "group" in data and "union" not in data:
            data = {**data, "union": data["group"]}
        # Рекурсивно парсим children через cls.from_dict (generic serde
        # не вызывает кастомный from_dict для вложенных dataclass'ов).
        raw_children = data.get("children")
        if isinstance(raw_children, list):
            parsed_children = [cls.from_dict(c) for c in raw_children if isinstance(c, dict)]
            data = {**data, "children": [c for c in parsed_children if c is not None]}
        # Devices тоже парсим через DeviceDto.from_dict (для name normalization).
        raw_devices = data.get("devices")
        if isinstance(raw_devices, list):
            parsed_devices = [DeviceDto.from_dict(d) for d in raw_devices if isinstance(d, dict)]
            data = {**data, "devices": [d for d in parsed_devices if d is not None]}
        union_raw = data.get("union")
        union = UnionDto.from_dict(union_raw) if isinstance(union_raw, dict) else None
        return cls(
            union=union,
            devices=data.get("devices", []),
            children=data.get("children", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["UnionDto", "UnionTreeDto", "UnionType"]
