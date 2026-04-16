"""Dataclass-модели для токенов: SberIdTokens, CompanionTokens.

Поля совпадают с wire-формой ответа `/CSAFront/.../token` (Sber ID) и
`/smarthome/token` (companion) для удобства roundtrip с from_dict/to_dict.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(slots=True)
class SberIdTokens:
    """Токены от id.sber.ru OAuth2 endpoint.

    `obtained_at` — Unix timestamp получения, заполняется автоматически.
    Свойство `expires_at` рассчитывается как `obtained_at + expires_in`.
    """

    access_token: str
    refresh_token: str | None = None
    id_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int = 3600  # секунды
    scope: str = ""
    obtained_at: float = field(default_factory=time.time)

    @property
    def expires_at(self) -> float:
        return self.obtained_at + self.expires_in

    def is_expired(self, leeway: float = 0) -> bool:
        return time.time() + leeway >= self.expires_at

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            id_token=data.get("id_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_in=int(data.get("expires_in", 3600)),
            scope=data.get("scope", ""),
            obtained_at=data.get("obtained_at", time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "id_token": self.id_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "scope": self.scope,
            "obtained_at": self.obtained_at,
        }


@dataclass(slots=True)
class CompanionTokens:
    """Токены от smarthome/token endpoint.

    Это то, что подписывает все запросы к gateway.iot.sberdevices.ru.
    Время жизни обычно дольше (24 часа), refresh механика — отдельный refresh_token.
    """

    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int = 86400
    obtained_at: float = field(default_factory=time.time)

    @property
    def expires_at(self) -> float:
        return self.obtained_at + self.expires_in

    def is_expired(self, leeway: float = 0) -> bool:
        return time.time() + leeway >= self.expires_at

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            token_type=data.get("token_type", "Bearer"),
            expires_in=int(data.get("expires_in", 86400)),
            obtained_at=data.get("obtained_at", time.time()),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_type": self.token_type,
            "expires_in": self.expires_in,
            "obtained_at": self.obtained_at,
        }
