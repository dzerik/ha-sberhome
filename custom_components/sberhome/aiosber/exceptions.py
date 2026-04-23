"""Exception hierarchy for aiosber.

Все ошибки наследуются от `SberError`. HA-адаптер мапит их на HA-исключения
(`ConfigEntryAuthFailed`, `ConfigEntryNotReady`, `UpdateFailed`) в одном месте.

Иерархия:

    SberError
    ├── AuthError          — OAuth/PKCE/refresh provoblems
    │   ├── InvalidGrant   — refresh token истёк или невалиден → reauth
    │   └── PkceError      — невалидный verifier/challenge или authorization code
    ├── NetworkError       — connect timeout, TLS, DNS, transient
    ├── ApiError           — server returned 4xx/5xx с ошибкой
    │   └── RateLimitError — 429 + Retry-After
    └── ProtocolError      — невалидный JSON, неизвестный серилизованный формат
"""

from __future__ import annotations


class SberError(Exception):
    """Base exception for aiosber."""


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class AuthError(SberError):
    """OAuth / PKCE / refresh failure."""


class InvalidGrant(AuthError):
    """Refresh token истёк/отозван — нужен полный re-auth."""


class PkceError(AuthError):
    """Невалидный code_verifier / code_challenge / authorization code."""


# ---------------------------------------------------------------------------
# Network
# ---------------------------------------------------------------------------
class NetworkError(SberError):
    """Transient network error: connect/read timeout, DNS, TLS."""


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
class ApiError(SberError):
    """Server returned an error response.

    Attributes:
        status_code: HTTP status (404, 500, ...).
        code:        Sber-specific error code (если присутствует в payload).
        message:     Человекочитаемое сообщение.
        payload:     Сырой error response (для диагностики).
    """

    def __init__(
        self,
        status_code: int,
        message: str = "",
        *,
        code: int | str | None = None,
        payload: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.payload = payload
        prefix = f"HTTP {status_code}"
        if code is not None:
            prefix += f" (code {code})"
        super().__init__(f"{prefix}: {message}" if message else prefix)


class RateLimitError(ApiError):
    """429 Too Many Requests. `retry_after` — секунды до повтора (если есть в headers)."""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        *,
        retry_after: float | None = None,
        payload: dict | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(429, message, payload=payload)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
class ProtocolError(SberError):
    """Невалидный серилизованный формат: невалидный JSON, отсутствующее обязательное поле."""
