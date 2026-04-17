"""Мост между `aiosber.DeviceDto` и `sbermap` value types.

Конвертит типизированный DTO устройства из aiosber в:
- `SberStateBundle` (для использования в transform / sber_to_ha)
- `list[HaEntityData]` (готовые HA-сущности через sber_to_ha + resolve_category)

Этот модуль — единственное место связи aiosber↔sbermap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..spec.ha_mapping import resolve_category
from ..values import (
    HsvColor,
    SberState,
    SberStateBundle,
    SberValue,
    ValueType,
)
from ._types import HaEntityData
from .sber_to_ha import sber_to_ha

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto
    from ...aiosber.dto.values import AttributeValueDto


def _attr_to_sber_value(av: AttributeValueDto) -> SberValue | None:
    """Преобразовать `AttributeValueDto` (aiosber) в `SberValue` (sbermap).

    Возвращает None если в DTO ни одно value-поле не заполнено.
    Schedule-значения пока не передаём — они не используются в transform-слое
    (HA не имеет matching entity-типа для расписаний).
    """
    if av.bool_value is not None:
        return SberValue(type=ValueType.BOOL, bool_value=av.bool_value)
    if av.integer_value is not None:
        return SberValue(type=ValueType.INTEGER, integer_value=av.integer_value)
    if av.float_value is not None:
        return SberValue(type=ValueType.FLOAT, float_value=av.float_value)
    if av.string_value is not None:
        return SberValue(type=ValueType.STRING, string_value=av.string_value)
    if av.enum_value is not None:
        return SberValue(type=ValueType.ENUM, enum_value=av.enum_value)
    if av.color_value is not None:
        cv = av.color_value
        return SberValue(
            type=ValueType.COLOR,
            color_value=HsvColor(
                hue=cv.hue, saturation=cv.saturation, brightness=cv.brightness
            ),
        )
    return None


def device_dto_to_state_bundle(device: DeviceDto) -> SberStateBundle:
    """Конверт DeviceDto → SberStateBundle.

    Объединяет `reported_state` + `desired_state` (последний имеет приоритет
    при коллизии ключей — desired = команда от пользователя, она авторитет
    для отображения в UI).
    """
    merged: dict[str, SberValue] = {}
    for av in device.reported_state:
        v = _attr_to_sber_value(av)
        if v is not None:
            merged[av.key] = v
    for av in device.desired_state:
        v = _attr_to_sber_value(av)
        if v is not None:
            merged[av.key] = v
    states = tuple(SberState(key=k, value=v) for k, v in merged.items())
    return SberStateBundle(device_id=device.id or "", states=states)


def device_dto_to_entities(device: DeviceDto) -> list[HaEntityData]:
    """DeviceDto → list[HaEntityData] через resolve_category + sber_to_ha.

    Возвращает пустой список если категория устройства не определена.
    """
    category = resolve_category(device.image_set_type)
    if category is None:
        return []
    name = device.display_name or device.id or "Sber Device"
    bundle = device_dto_to_state_bundle(device)
    return sber_to_ha(category, device.id or "", name, bundle)


__all__ = [
    "device_dto_to_entities",
    "device_dto_to_state_bundle",
]
