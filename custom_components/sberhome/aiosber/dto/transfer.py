"""HomeTransferBaseDto — передача дома между пользователями.

JSON schema: поле ``home_transfer`` в SocketMessageDto (WS topic HOME_TRANSFER).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class HomeTransferBaseDto:
    """Передача/приём дома из WS push.

    В APIе это sealed class с подтипами (receive/transfer).
    Минимальная типизация с type-дискриминатором.
    """

    type: str | None = None
    to_user_id: str | None = None
    from_user_id: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["HomeTransferBaseDto"]
