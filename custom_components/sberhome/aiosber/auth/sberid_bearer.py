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
        # Single-flight: число завершённых попыток refresh и ошибка последней
        # (см. `_refresh_locked`).
        self._refresh_attempts = 0
        self._last_refresh_error: Exception | None = None

    async def access_token(self) -> str:
        """Вернуть валидный SberID access_token, обновив его при истечении.

        Raises:
            InvalidGrant: refresh_token отсутствует или отозван.
        """
        if not self._tokens.is_expired(self._leeway):
            return self._tokens.access_token
        seen_attempt = self._refresh_attempts
        async with self._lock:
            if not self._tokens.is_expired(self._leeway):
                return self._tokens.access_token
            await self._refresh_locked(seen_attempt)
            return self._tokens.access_token

    async def force_refresh(self, stale_token: str | None = None) -> None:
        """Принудительно обновить SberID-токены (HttpTransport при 401).

        Args:
            stale_token: access_token, с которым запрос получил отказ. Если
                соседний запрос уже обновил токены, refresh не выполняется —
                одноразовый refresh_token ротируется и сохраняется один раз.
                ``None`` — обновить безусловно.

        Raises:
            InvalidGrant: refresh_token отсутствует или отозван.
        """
        seen_attempt = self._refresh_attempts
        async with self._lock:
            if stale_token is not None and self._tokens.access_token != stale_token:
                return
            await self._refresh_locked(seen_attempt)

    async def _refresh_locked(self, seen_attempt: int) -> None:
        """Выполнить refresh под `self._lock`, разделяя неудачу с ждавшими.

        Args:
            seen_attempt: значение `_refresh_attempts` до ожидания lock. Если
                за время ожидания соседняя задача уже пыталась обновить токены
                и упала — её ошибка пробрасывается без повторного refresh.

        Raises:
            InvalidGrant / AuthError / NetworkError: ошибка refresh.
        """
        err = self._last_refresh_error
        # InvalidGrant — отказ окончательный (одноразовый refresh_token отозван):
        # повтор с теми же учётными данными гарантированно упадёт, а до reauth
        # каждый запрос бил бы в Sber. Прочие ошибки делятся только с теми, кто
        # ждал lock во время неудачной попытки.
        if err is not None and (
            seen_attempt != self._refresh_attempts or isinstance(err, InvalidGrant)
        ):
            raise err
        self._last_refresh_error = None
        try:
            await self._refresh()
        except Exception as exc:
            self._last_refresh_error = exc
            raise
        else:
            self._last_refresh_error = None
        finally:
            # Считаем ЗАВЕРШЁННЫЕ попытки: задачи, вставшие в очередь во время
            # этой, видят прежнее значение и узнают о её исходе.
            self._refresh_attempts += 1

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
