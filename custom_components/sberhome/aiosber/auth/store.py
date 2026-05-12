"""TokenStore — Protocol-ы для хранения токенов.

Два независимых протокола под два auth path'а:
- `TokenStore` — companion-токены (SberID OAuth flow).
- `CsafrontTokenStore` — CsafrontTokens (SMS-OTP beta flow).

Имплементации:
- `InMemoryTokenStore` / `InMemoryCsafrontTokenStore` — для тестов / CLI.
- HA-адаптер реализует свои store-ы поверх `config_entry.data` (см.
  `_ha_token_store.py`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .tokens import CompanionTokens, CsafrontTokens


@runtime_checkable
class AuthManagerProtocol(Protocol):
    """Duck-typed interface для `HttpTransport.auth`.

    Реализуется и `AuthManager` (SberID + companion flow), и
    `CsafrontAuthManager` (SMS-OTP beta flow). HttpTransport не должен
    знать о деталях flow — ему достаточно валидного токена.
    """

    async def access_token(self) -> str: ...
    async def force_refresh(self) -> None: ...


class TokenStore(Protocol):
    """Async-хранилище companion-токенов.

    Контракт:
    - `load()` возвращает None если токенов ещё нет (или они стёрты).
    - `save()` атомарно перезаписывает; не должен бросать на «уже есть».
    - `clear()` идемпотентен — не бросает если токенов нет.
    """

    async def load(self) -> CompanionTokens | None: ...
    async def save(self, tokens: CompanionTokens) -> None: ...
    async def clear(self) -> None: ...


class CsafrontTokenStore(Protocol):
    """Async-хранилище CSAFront SMS-OTP токенов (beta).

    Тот же контракт что у TokenStore, но другой shape данных.
    Разнесён в отдельный протокол — компилятор/тесты ловят перепутанные
    шкафы (нельзя случайно подсунуть companion-store в CSAFront менеджер).
    """

    async def load(self) -> CsafrontTokens | None: ...
    async def save(self, tokens: CsafrontTokens) -> None: ...
    async def clear(self) -> None: ...


class InMemoryTokenStore:
    """In-memory имплементация TokenStore.

    Подходит для тестов и одноразовых CLI-скриптов.
    Для HA / CLI с persistence использовать другие имплементации.

    Можно инициализировать с предустановленным токеном:

        store = InMemoryTokenStore(initial=CompanionTokens(access_token="..."))
    """

    __slots__ = ("_tokens",)

    def __init__(self, initial: CompanionTokens | None = None) -> None:
        self._tokens: CompanionTokens | None = initial

    async def load(self) -> CompanionTokens | None:
        return self._tokens

    async def save(self, tokens: CompanionTokens) -> None:
        self._tokens = tokens

    async def clear(self) -> None:
        self._tokens = None


class InMemoryCsafrontTokenStore:
    """In-memory имплементация CsafrontTokenStore (для тестов / CLI)."""

    __slots__ = ("_tokens",)

    def __init__(self, initial: CsafrontTokens | None = None) -> None:
        self._tokens: CsafrontTokens | None = initial

    async def load(self) -> CsafrontTokens | None:
        return self._tokens

    async def save(self, tokens: CsafrontTokens) -> None:
        self._tokens = tokens

    async def clear(self) -> None:
        self._tokens = None
