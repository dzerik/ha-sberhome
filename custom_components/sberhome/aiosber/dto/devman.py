"""DevmanDto — события устройств (кнопки, алармы).

Wire: поле ``event`` в SocketMessageDto (WS topic DEVMAN_EVENT).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class DevmanDto:
    """Событие устройства из WS push.

    Поля ``device`` и ``group`` — вложенные объекты, оставлены
    как dict (структура варьируется между типами событий).
    """

    type: str | None = None
    device_id: str | None = None
    device: dict[str, Any] | None = None
    group: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["DevmanDto"]
