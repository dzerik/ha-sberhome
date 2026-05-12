"""Dataclass-модели для токенов: SberIdTokens, CompanionTokens, CsafrontTokens.

Поля совпадают с API-формой ответа `/CSAFront/.../token` (Sber ID) и
`/smarthome/token` (companion) для удобства roundtrip с from_dict/to_dict.

CsafrontTokens — beta SMS-OTP auth path: пара CSAFront access+refresh +
SmartHomeToken (используется как X-AUTH-jwt напрямую).
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


@dataclass(slots=True)
class CsafrontTokens:
    """Токены SMS-OTP CSAFront flow (beta).

    Содержит:
    - `csafront_access_token` / `csafront_refresh_token` — OIDC токены от
      `online.sberbank.ru/CSAFront/.../oidc/v3/token`. **Refresh rotation** —
      каждое использование refresh_token revoke'ит старый, поэтому
      обязательно persist'им новый refresh_token после каждого обновления.
    - `smart_home_token` — выдаётся `mp-prom.salutehome.ru/v13/smarthome/token`
      по CSAFront access_token. Используется как X-AUTH-jwt для
      `gateway.iot.sberdevices.ru` напрямую — без отдельного companion
      обмена.
    - `client_uuid` — persistent UUID (X-Device-ID); привязывается к
      сессии на сервере, должен быть стабилен между запросами.
    - `phone` — телефон в формате E.164 без `+` (78001002030), хранится
      для информативности UI; не используется для refresh.
    """

    csafront_access_token: str
    csafront_refresh_token: str
    smart_home_token: str
    client_uuid: str
    csafront_expires_in: int = 1800  # типично 30 минут
    csafront_obtained_at: float = field(default_factory=time.time)
    smart_home_obtained_at: float = field(default_factory=time.time)
    phone: str | None = None

    @property
    def csafront_expires_at(self) -> float:
        return self.csafront_obtained_at + self.csafront_expires_in

    def is_csafront_expired(self, leeway: float = 0) -> bool:
        return time.time() + leeway >= self.csafront_expires_at

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        return cls(
            csafront_access_token=data["csafront_access_token"],
            csafront_refresh_token=data["csafront_refresh_token"],
            smart_home_token=data["smart_home_token"],
            client_uuid=data["client_uuid"],
            csafront_expires_in=int(data.get("csafront_expires_in", 1800)),
            csafront_obtained_at=float(data.get("csafront_obtained_at", time.time())),
            smart_home_obtained_at=float(data.get("smart_home_obtained_at", time.time())),
            phone=data.get("phone"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "csafront_access_token": self.csafront_access_token,
            "csafront_refresh_token": self.csafront_refresh_token,
            "smart_home_token": self.smart_home_token,
            "client_uuid": self.client_uuid,
            "csafront_expires_in": self.csafront_expires_in,
            "csafront_obtained_at": self.csafront_obtained_at,
            "smart_home_obtained_at": self.smart_home_obtained_at,
            "phone": self.phone,
        }
