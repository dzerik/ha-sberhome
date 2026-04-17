"""GroupStateDto — состояние группы устройств.

Wire: поле ``group_state`` в SocketMessageDto (WS topic GROUP_STATE).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class GroupStateDto:
    """Состояние группы из WS push.

    ``status`` оставлен как dict — внутренняя структура StatusDto
    варьируется и редко нужна интеграции.
    """

    type: str | None = None
    id: str | None = None
    status: dict[str, Any] | None = None
    updated_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        # Wire uses camelCase: updatedAt
        if isinstance(data, dict) and "updatedAt" in data and "updated_at" not in data:
            data = {**data, "updated_at": data["updatedAt"]}
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["GroupStateDto"]
