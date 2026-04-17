"""Контейнеры для команд (desired_state) и WS state-сообщений.

PUT /gateway/v1/devices/{id}/state принимает DesiredDeviceStateDto.
WebSocket топик DEVICE_STATE приносит StateDto.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .enums import ElementType
from .values import AttributeValueDto


@dataclass(slots=True, frozen=True)
class DesiredDeviceStateDto:
    """Body для PUT /gateway/v1/devices/{id}/state.

    Пример:

        body = DesiredDeviceStateDto(desired_state=[
            AttributeValueDto.of_bool("on_off", True),
            AttributeValueDto.of_int("light_brightness", 500),
        ])
        await client.put(f"devices/{device_id}/state", json=body.to_dict())
    """

    desired_state: list[AttributeValueDto] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class DesiredGroupStateDto:
    """Body для PUT /gateway/v1/device_groups/{id}/state."""

    desired_state: list[AttributeValueDto] = field(default_factory=list)
    return_group_status: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class StateDto:
    """Сообщение DEVICE_STATE из WebSocket (`SocketMessageDto.state`).

    Wire-формат (подтверждён анализом клиентского стека):
    ``{"device_id": "abc", "reported_state": [...], "timestamp": "..."}``

    Поле `device_id` присутствует в WS push-сообщениях — это primary
    source для идентификации устройства при точечном state-патче.
    """

    device_id: str | None = None
    reported_state: list[AttributeValueDto] = field(default_factory=list)
    timestamp: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class DeviceOrderElement:
    """Элемент списка для PUT devices/order."""

    id: str
    type: ElementType

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)
