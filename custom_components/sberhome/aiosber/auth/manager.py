"""AuthManager — lifecycle токенов с auto-refresh.

Обязанности:
- Хранить SberID и Companion токены через инжектируемый `TokenStore`.
- Возвращать валидный companion access_token по запросу (`access_token()`).
- Автоматически обмениваться refresh_token при истечении.
- Сериализовать конкурентные refresh через asyncio.Lock (защита от шторма).
- Поднимать `InvalidGrant` если refresh невозможен → HA-адаптер инициирует reauth.

Текущая ограничение: companion token endpoint не возвращает свой refresh_token
в стабильном виде (поведение зависит от реализации Sber). При истечении
companion-токена единственная надёжная стратегия — повторный обмен через
**SberID refresh** + новый `exchange_for_companion_token()`. Поэтому
AuthManager хранит **обе** пары токенов.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from ..const import (
    COMPANION_BASE_URL,
    COMPANION_TOKEN_PATH,
    DEFAULT_CLIENT_ID,
    TOKEN_ENDPOINT,
    TOKEN_EXPIRY_LEEWAY_S,
)
from ..exceptions import AuthError, InvalidGrant
from .companion import exchange_for_companion_token
from .oauth import refresh_sberid_tokens
from .store import TokenStore
from .tokens import CompanionTokens, SberIdTokens

SberIdRefreshCallback = Callable[[SberIdTokens], Awaitable[None]]
"""Callback, который вызывается после каждой успешной ротации SberID-токенов.

HA-адаптер использует это, чтобы писать новый SberID-токен в
`config_entry.data["token"]` — иначе ротированный refresh_token теряется,
и после рестарта HA интеграция не может обменять токены и падает в reauth.
"""

_LOGGER = logging.getLogger(__name__)


class AuthManager:
    """Provides valid companion `access_token` on demand, refreshing as needed.

    Args:
        http: shared httpx.AsyncClient.
        store: TokenStore для companion-токенов.
        sberid_tokens: текущие SberID токены (если уже есть).
            Можно установить позже через `set_sberid_tokens()`.
        client_id: OAuth client_id для refresh.
        token_endpoint: override SberID token endpoint.
        companion_endpoint: override companion `/smarthome/token` endpoint.
        leeway: насколько секунд раньше истечения инициировать refresh.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        store: TokenStore,
        *,
        sberid_tokens: SberIdTokens | None = None,
        client_id: str = DEFAULT_CLIENT_ID,
        token_endpoint: str = TOKEN_ENDPOINT,
        companion_endpoint: str = COMPANION_BASE_URL + COMPANION_TOKEN_PATH,
        leeway: float = TOKEN_EXPIRY_LEEWAY_S,
        on_sberid_refreshed: SberIdRefreshCallback | None = None,
    ) -> None:
        self._http = http
        self._store = store
        self._sberid: SberIdTokens | None = sberid_tokens
        self._companion: CompanionTokens | None = None
        self._client_id = client_id
        self._token_endpoint = token_endpoint
        self._companion_endpoint = companion_endpoint
        self._leeway = leeway
        self._on_sberid_refreshed = on_sberid_refreshed
        self._lock = asyncio.Lock()
        self._loaded = False

    # ----- Public API -----
    async def access_token(self) -> str:
        """Return valid companion access_token, refreshing if needed.

        Raises:
            InvalidGrant: refresh невозможен — нужен полный re-auth пользователя.
            AuthError: другие auth-проблемы.
        """
        await self._ensure_loaded()
        if self._companion and not self._companion.is_expired(self._leeway):
            return self._companion.access_token

        async with self._lock:
            # Double-check после lock — возможно соседний task уже обновил
            if self._companion and not self._companion.is_expired(self._leeway):
                return self._companion.access_token
            await self._refresh_companion()
            assert self._companion is not None  # _refresh_companion гарантирует
            return self._companion.access_token

    async def force_refresh(self) -> None:
        """Принудительно обновить companion-токен.

        Используется HttpTransport'ом при получении 401 (даже если по сроку
        токен ещё валиден — мог быть отозван на сервере).
        """
        await self._ensure_loaded()
        async with self._lock:
            await self._refresh_companion()

    def set_sberid_tokens(self, tokens: SberIdTokens) -> None:
        """Установить новые SberID-токены (например, после первого OAuth-flow)."""
        self._sberid = tokens

    def set_companion_tokens(self, tokens: CompanionTokens) -> None:
        """Установить новые companion-токены (после первого обмена)."""
        self._companion = tokens

    async def persist(self) -> None:
        """Сохранить текущие companion-токены в store."""
        if self._companion is not None:
            await self._store.save(self._companion)

    async def clear(self) -> None:
        """Стереть токены отовсюду (для logout)."""
        self._companion = None
        self._sberid = None
        await self._store.clear()

    @property
    def has_companion(self) -> bool:
        return self._companion is not None

    @property
    def has_sberid_refresh(self) -> bool:
        return self._sberid is not None and bool(self._sberid.refresh_token)

    @property
    def sberid_expires_at(self) -> float | None:
        """Unix timestamp истечения SberID-токена; None если токен не загружен."""
        return self._sberid.expires_at if self._sberid is not None else None

    @property
    def companion_expires_at(self) -> float | None:
        """Unix timestamp истечения companion-токена; None если ещё не получен."""
        return self._companion.expires_at if self._companion is not None else None

    # ----- Internal -----
    async def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if not self._loaded:
                stored = await self._store.load()
                if stored is not None:
                    self._companion = stored
                self._loaded = True

    async def _refresh_companion(self) -> None:
        """Получить новый companion-токен.

        Стратегия:
        1. Если есть валидные SberID токены — обменять их.
        2. Если SberID истёк, но есть refresh_token — refresh SberID + retry.
        3. Иначе — InvalidGrant (нужен полный reauth).
        """
        # Шаг 1: убедиться что SberID живой
        if self._sberid is None:
            raise InvalidGrant("No SberID tokens — full re-auth required")

        if self._sberid.is_expired(self._leeway):
            if not self._sberid.refresh_token:
                raise InvalidGrant("SberID expired and no refresh_token")
            _LOGGER.debug("Refreshing SberID tokens")
            self._sberid = await refresh_sberid_tokens(
                self._http,
                self._sberid.refresh_token,
                client_id=self._client_id,
                endpoint=self._token_endpoint,
            )
            await self._notify_sberid_refreshed()

        # Шаг 2: обменять SberID на companion
        _LOGGER.debug("Exchanging SberID access for companion token")
        try:
            self._companion = await exchange_for_companion_token(
                self._http,
                self._sberid.access_token,
                endpoint=self._companion_endpoint,
            )
        except AuthError:
            # Companion endpoint отверг наш SberID — попробуем refresh SberID и повторить
            if self._sberid.refresh_token:
                _LOGGER.info("Companion exchange rejected, refreshing SberID and retrying")
                self._sberid = await refresh_sberid_tokens(
                    self._http,
                    self._sberid.refresh_token,
                    client_id=self._client_id,
                    endpoint=self._token_endpoint,
                )
                await self._notify_sberid_refreshed()
                self._companion = await exchange_for_companion_token(
                    self._http,
                    self._sberid.access_token,
                    endpoint=self._companion_endpoint,
                )
            else:
                raise InvalidGrant(
                    "Companion exchange failed and no SberID refresh_token"
                ) from None

        await self._store.save(self._companion)

    async def _notify_sberid_refreshed(self) -> None:
        """Уведомить HA-адаптер о ротации SberID-токенов.

        Refresh_token у Sber ротируется (OAuth2 best practice) — без persist'а
        в config_entry.data после рестарта HA используется устаревший
        refresh_token, что приводит к `InvalidGrant` и forced reauth.
        Callback не должен падать: ошибки логируются, но не пропагируются.
        """
        if self._on_sberid_refreshed is None or self._sberid is None:
            return
        try:
            await self._on_sberid_refreshed(self._sberid)
        except Exception:  # noqa: BLE001 — persist best-effort, не ломаем auth flow
            _LOGGER.exception("on_sberid_refreshed callback failed")
