"""WS push application helpers (PR #11).

Применение DEVICE_STATE push'а из WebSocket напрямую к coordinator-кэшу,
без полного REST refresh. Inputs:
- `device_id` (из SocketMessageDto.target_device_id или fallback).
- `reported_state` list[AttributeValueDto] (из StateDto).

Возвращает обновлённый `DeviceDto` (immutable). Caller должен сам
обновить coordinator.devices[id] и пересобрать entities.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto
    from ...aiosber.dto.values import AttributeValueDto


def apply_reported_state(
    dto: DeviceDto,
    reported_state: list[AttributeValueDto],
) -> DeviceDto:
    """Apply WS reported_state поверх DTO. Возвращает новый DTO (immutable).

    Если в `reported_state` есть ключ, который уже есть в `dto.reported_state`
    — заменяем; новые ключи добавляем в конец. Поле `desired_state` НЕ
    трогаем (WS DEVICE_STATE — это reported, не команда).
    """
    if not reported_state:
        return dto
    by_key = {av.key: av for av in dto.reported_state}
    for av in reported_state:
        if av.key:
            by_key[av.key] = av
    new_list = list(by_key.values())
    return replace(dto, reported_state=new_list)


__all__ = ["apply_reported_state"]
