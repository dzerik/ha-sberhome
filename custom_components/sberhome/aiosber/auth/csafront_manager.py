"""CsafrontAuthManager — lifecycle для SMS-OTP auth path (beta).

Тот же публичный API что у `AuthManager`:
- `async access_token() -> str` — валидный SmartHomeToken (X-AUTH-jwt).
- `async force_refresh() -> None` — принудительно обновить пару.

Стратегия refresh:
1. CSAFront access_token истёк → используем CSAFront refresh_token
   (refresh с rotation: новый refresh_token заменяет старый).
2. CSAFront refresh успешен → запрашиваем новый SmartHomeToken.
3. Если CSAFront refresh упал invalid_grant → InvalidGrant (нужен
   полный re-auth через SMS).

В отличие от стандартного `AuthManager`, здесь НЕТ обмена SberID →
companion. Cmart_home_token получается напрямую CSAFront access → GET
`/v13/smarthome/token`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

import httpx

from ..const import TOKEN_EXPIRY_LEEWAY_S
from ..exceptions import InvalidGrant
from .csafront import get_smart_home_token, refresh_csafront
from .store import CsafrontTokenStore
from .tokens import CsafrontTokens

CsafrontTokensRefreshedCallback = Callable[[CsafrontTokens], Awaitable[None]]
"""Callback, который вызывается после каждой успешной ротации CSAFront-токенов.

HA-адаптер использует это, чтобы писать новый CsafrontTokens в
`config_entry.data` — иначе ротированный refresh_token теряется и
после рестарта HA интеграция падает в reauth.
"""

_LOGGER = logging.getLogger(__name__)


class CsafrontAuthManager:
    """SMS-OTP auth manager — выдаёт SmartHomeToken как X-AUTH-jwt.

    Args:
        http: shared httpx.AsyncClient.
        store: CsafrontTokenStore для persist'а пары токенов.
        initial: текущие токены, если уже есть (например после первичного
            SMS-flow). Можно установить позже через `set_tokens()`.
        leeway: насколько секунд раньше истечения CSAFront access_token
            инициировать refresh.
        on_tokens_refreshed: callback после успешной ротации (HA-адаптер
            пишет в config_entry.data).
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        store: CsafrontTokenStore,
        *,
        initial: CsafrontTokens | None = None,
        leeway: float = TOKEN_EXPIRY_LEEWAY_S,
        on_tokens_refreshed: CsafrontTokensRefreshedCallback | None = None,
    ) -> None:
        self._http = http
        self._store = store
        self._tokens: CsafrontTokens | None = initial
        self._leeway = leeway
        self._on_refreshed = on_tokens_refreshed
        self._lock = asyncio.Lock()
        self._loaded = initial is not None

    # ----- Public API (mirror of AuthManager) -----
    async def access_token(self) -> str:
        """Return valid SmartHomeToken, refreshing CSAFront pair if expired.

        Raises:
            InvalidGrant: refresh_token уже отозван — нужен полный
                SMS-OTP flow заново.
        """
        await self._ensure_loaded()
        if self._tokens is None:
            raise InvalidGrant("CSAFront: no tokens — re-auth required")

        # CSAFront access короткоживущий (~30 мин). SmartHomeToken тоже
        # имеет TTL, но мы обновляем его вместе с CSAFront, поэтому
        # достаточно отслеживать CSAFront expiry.
        if not self._tokens.is_csafront_expired(self._leeway):
            return self._tokens.smart_home_token

        async with self._lock:
            # double-check после lock
            if self._tokens and not self._tokens.is_csafront_expired(self._leeway):
                return self._tokens.smart_home_token
            await self._refresh_tokens()
            assert self._tokens is not None
            return self._tokens.smart_home_token

    async def force_refresh(self) -> None:
        """Принудительно обновить пару (CSAFront + SmartHomeToken).

        Вызывается HttpTransport при 401/403 от gateway, даже если по TTL
        токен ещё считался валидным.
        """
        await self._ensure_loaded()
        async with self._lock:
            await self._refresh_tokens()

    def set_tokens(self, tokens: CsafrontTokens) -> None:
        """Установить новые токены (например после успешного SMS-OTP flow)."""
        self._tokens = tokens
        self._loaded = True

    async def persist(self) -> None:
        """Сохранить текущие токены в store."""
        if self._tokens is not None:
            await self._store.save(self._tokens)

    async def clear(self) -> None:
        """Стереть токены отовсюду (для logout)."""
        self._tokens = None
        await self._store.clear()

    @property
    def has_tokens(self) -> bool:
        return self._tokens is not None

    @property
    def smart_home_expires_at(self) -> float | None:
        """Unix timestamp истечения CSAFront access_token (proxy для
        smart_home_token TTL)."""
        return self._tokens.csafront_expires_at if self._tokens is not None else None

    # ----- Internal -----
    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if not self._loaded:
                stored = await self._store.load()
                if stored is not None:
                    self._tokens = stored
                self._loaded = True

    async def _refresh_tokens(self) -> None:
        """Обновить CSAFront пару + новый SmartHomeToken.

        Refresh rotation: новый refresh_token (если backend отдал)
        заменяет старый. Persist'им сразу — иначе следующий запуск HA
        потеряет ротированный токен и получит invalid_grant.
        """
        if self._tokens is None:
            raise InvalidGrant("CSAFront: no tokens to refresh — re-auth required")

        _LOGGER.debug("CSAFront: refreshing access_token via refresh_token rotation")
        try:
            new = await refresh_csafront(self._http, self._tokens.csafront_refresh_token)
        except InvalidGrant:
            # Refresh_token уже отозван — нужен полный SMS-OTP flow.
            _LOGGER.warning("CSAFront refresh_token rejected, full re-auth needed")
            raise

        new_access = new["access_token"]
        # rotation: backend может вернуть новый refresh, может оставить
        # старый (см. spec.). Если новый есть — используем, иначе — старый.
        new_refresh = new.get("refresh_token") or self._tokens.csafront_refresh_token
        expires_in = int(new.get("expires_in", self._tokens.csafront_expires_in))

        _LOGGER.debug("CSAFront: fetching new smart_home_token")
        new_smart = await get_smart_home_token(self._http, new_access)

        now = time.time()
        self._tokens = CsafrontTokens(
            csafront_access_token=new_access,
            csafront_refresh_token=new_refresh,
            smart_home_token=new_smart,
            client_uuid=self._tokens.client_uuid,
            csafront_expires_in=expires_in,
            csafront_obtained_at=now,
            smart_home_obtained_at=now,
            phone=self._tokens.phone,
        )
        await self._store.save(self._tokens)
        await self._notify_refreshed()

    async def _notify_refreshed(self) -> None:
        """Уведомить HA-адаптер о ротации (для persist в config_entry.data)."""
        if self._on_refreshed is None or self._tokens is None:
            return
        try:
            await self._on_refreshed(self._tokens)
        except Exception:  # noqa: BLE001 — persist best-effort
            _LOGGER.exception("CSAFront on_tokens_refreshed callback failed")


__all__ = ["CsafrontAuthManager", "CsafrontTokensRefreshedCallback"]
