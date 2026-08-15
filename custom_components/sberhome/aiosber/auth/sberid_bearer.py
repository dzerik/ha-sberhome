"""SberIdBearerAuth — провайдер СЫРОГО SberID access_token.

Некоторым каналам нужен именно SberID access_token (клиент b1f0f0c6) в виде
`Authorization: Bearer <...>`, а не обменянный на нём companion smart_home-токен.
`AuthManager` отдаёт как раз companion-токен (после обмена), поэтому для таких
каналов используется этот отдельный лёгкий провайдер: он возвращает сам SberID
access_token и обновляет его через `refresh_sberid_tokens` при истечении.

Реализует тот же контракт, что `AuthManagerProtocol` (`access_token()` /
`force_refresh()`), поэтому подходит для `HttpTransport`.

ZERO HA imports.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Final

import httpx

from ..const import DEFAULT_CLIENT_ID, TOKEN_ENDPOINT, TOKEN_EXPIRY_LEEWAY_S
from ..exceptions import InvalidGrant
from .oauth import refresh_sberid_tokens
from .tokens import SberIdTokens

SberIdRefreshedCallback = Callable[[SberIdTokens], Awaitable[None]]


class SberIdBearerAuth:
    """Отдаёт валидный SberID access_token, обновляя его по необходимости.

    Args:
        http: shared httpx.AsyncClient (DI).
        tokens: текущие SberID токены (access + refresh).
        on_refreshed: callback после ротации (HA-адаптер персистит в entry.data).
        leeway: запас по времени до истечения, при котором инициируется refresh.
        client_id / endpoint: параметры OAuth-refresh (по умолчанию b1f0f0c6).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        tokens: SberIdTokens,
        *,
        on_refreshed: SberIdRefreshedCallback | None = None,
        leeway: float = TOKEN_EXPIRY_LEEWAY_S,
        client_id: str = DEFAULT_CLIENT_ID,
        endpoint: str = TOKEN_ENDPOINT,
    ) -> None:
        self._http = http
        self._tokens: SberIdTokens = tokens
        self._on_refreshed = on_refreshed
        self._leeway: Final = leeway
        self._client_id = client_id
        self._endpoint = endpoint
        self._lock = asyncio.Lock()

    async def access_token(self) -> str:
        if not self._tokens.is_expired(self._leeway):
            return self._tokens.access_token
        async with self._lock:
            if not self._tokens.is_expired(self._leeway):
                return self._tokens.access_token
            await self._refresh()
            return self._tokens.access_token

    async def force_refresh(self) -> None:
        async with self._lock:
            await self._refresh()

    async def _refresh(self) -> None:
        refresh_token = self._tokens.refresh_token
        if not refresh_token:
            raise InvalidGrant("SberID refresh_token missing — reauth required")
        new = await refresh_sberid_tokens(
            self._http, refresh_token, client_id=self._client_id, endpoint=self._endpoint
        )
        # Refresh rotation: если backend не вернул новый refresh_token — оставляем
        # прежний, иначе следующий refresh получит пустой токен.
        if not new.refresh_token:
            new = SberIdTokens(
                access_token=new.access_token,
                refresh_token=refresh_token,
                id_token=new.id_token,
                scope=new.scope,
                token_type=new.token_type,
                expires_in=new.expires_in,
                obtained_at=new.obtained_at,
            )
        self._tokens = new
        if self._on_refreshed is not None:
            await self._on_refreshed(self._tokens)


__all__ = ["SberIdBearerAuth", "SberIdRefreshedCallback"]
