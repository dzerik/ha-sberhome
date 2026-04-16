"""TokenStore — Protocol для хранения CompanionTokens.

Имплементации:
- `InMemoryTokenStore` — для тестов и CLI-сценариев.
- HA-адаптер реализует свой store на base of `config_entry.data` (см. ha_adapter.py).
- Файловое хранилище — TODO (отдельный модуль `file_store.py` в PR #2).
"""

from __future__ import annotations

from typing import Protocol

from .tokens import CompanionTokens


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
