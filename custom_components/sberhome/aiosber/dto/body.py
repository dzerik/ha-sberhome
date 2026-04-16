"""Тела HTTP-запросов к gateway/v1/devices/* и device_groups/*."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .device import IndicatorColor
from .state import DeviceOrderElement


@dataclass(slots=True, frozen=True)
class UpdateNameBody:
    """PUT devices/{id}/name."""

    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class UpdateParentBody:
    """PUT devices/{id}/parent.

    parent_id=None означает «вынести из группы».
    """

    parent_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class DeviceToPairingBody:
    """POST devices/pairing — поставить устройство в режим pairing.

    Поля частично восстановлены из wire-протокола; могут потребоваться доп. ключи
    в зависимости от типа устройства (Wi-Fi vs Zigbee vs Matter).
    """

    device_id: str | None = None
    image_set_type: str | None = None
    pairing_type: str | None = None  # "wifi" | "zigbee" | "matter"
    timeout: int | None = None
    extra: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class CreateDeviceLinkBody:
    """POST devices/{id}/link."""

    type: str  # см. DeviceLinkType (но wire-string)
    from_device_id: str
    to_device_id: str

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class ChangeDeviceOrderElementsBody:
    """PUT devices/order — переупорядочить устройства/группы."""

    elements: list[DeviceOrderElement] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class IndicatorColorBody:
    """PUT devices/indicator/values."""

    indicator_color: IndicatorColor

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)
