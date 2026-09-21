"""AuthManager — lifecycle токенов с auto-refresh.

Обязанности:
- Хранить SberID и Companion токены через инжектируемый `TokenStore`.
- Возвращать валидный companion access_token по запросу (`access_token()`).
- Автоматически обмениваться refresh_token при истечении.
- Сериализовать конкурентные refresh через asyncio.Lock (защита от шторма):
  параллельные 401 с одним и тем же токеном дают один refresh.
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
from ._single_flight import SingleFlightRefresh
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
        # Single-flight: N параллельных refresh дают один обмен; задача, ждавшая
        # lock, пока соседняя безуспешно обновляла токен, получает ту же ошибку.
        self._single_flight = SingleFlightRefresh(self._lock, self._refresh_companion)
        # Отдельный single-flight для ротации ТОЛЬКО SberID-токена (без обмена
        # на companion). Каналы, которым нужен сырой SberID access_token
        # (настройки колонок), делят с companion-веткой один и тот же
        # одноразовый refresh_token. Поэтому ротация обязана идти через ЕДИНОГО
        # владельца — этот AuthManager: иначе два независимых refresh'а гонятся
        # за один refresh_token и тот, что обновляется вторым, ловит
        # invalid_grant. Общий `self._lock` сериализует обе ветки, а skip-проверка
        # под lock не даёт двойной ротации.
        self._sberid_single_flight = SingleFlightRefresh(self._lock, self._refresh_sberid_only)

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

        # Double-check под lock — возможно соседний task уже обновил
        await self._single_flight.run(
            skip=lambda: (
                self._companion is not None and not self._companion.is_expired(self._leeway)
            )
        )
        assert self._companion is not None  # _refresh_companion гарантирует
        return self._companion.access_token

    async def force_refresh(self, stale_token: str | None = None) -> None:
        """Принудительно обновить companion-токен.

        Используется HttpTransport'ом при получении 401 (даже если по сроку
        токен ещё валиден — мог быть отозван на сервере).

        Args:
            stale_token: access_token, с которым запрос получил отказ. Если к
                моменту захвата lock текущий токен уже другой (соседний запрос
                успел обновить), refresh не выполняется — N параллельных 401
                дают один обмен и одну запись токенов. ``None`` — обновить
                безусловно.

        Raises:
            InvalidGrant: refresh невозможен — нужен полный re-auth.
            AuthError: другие auth-проблемы.
        """
        await self._ensure_loaded()
        await self._single_flight.run(
            skip=lambda: (
                stale_token is not None
                and self._companion is not None
                and self._companion.access_token != stale_token
            )
        )

    async def sberid_access_token(self) -> str:
        """Вернуть валидный СЫРОЙ SberID access_token (клиент b1f0f0c6).

        Для каналов, которым нужен сам SberID-токен, а не обменянный на него
        companion smart_home-токен (например домен настроек колонок). Делит
        ОДИН экземпляр SberID-токенов и один refresh с companion-веткой —
        единый владелец ротации, без гонки за одноразовый refresh_token.

        Raises:
            InvalidGrant: SberID-токенов нет или refresh невозможен — reauth.
        """
        if self._sberid is not None and not self._sberid.is_expired(self._leeway):
            return self._sberid.access_token
        await self._sberid_single_flight.run(
            skip=lambda: self._sberid is not None and not self._sberid.is_expired(self._leeway)
        )
        if self._sberid is None:
            raise InvalidGrant("No SberID tokens — full re-auth required")
        return self._sberid.access_token

    async def force_refresh_sberid(self, stale_token: str | None = None) -> None:
        """Принудительно ротировать SberID-токен (для 401 в канале настроек).

        Args:
            stale_token: SberID access_token, получивший 401. Если к моменту
                захвата lock он уже заменён (companion-ветка или соседний
                запрос успели ротировать) — refresh не выполняется.
        """
        await self._sberid_single_flight.run(
            skip=lambda: (
                stale_token is not None
                and self._sberid is not None
                and self._sberid.access_token != stale_token
            )
        )

    def sberid_bearer(self) -> _SberIdBearerView:
        """Адаптер под `AuthManagerProtocol`, отдающий сырой SberID access_token.

        Плагается в `HttpTransport` для каналов, которым нужен SberID-токен, а
        не companion. Делегирует в этот же AuthManager — единый владелец
        ротации SberID (см. `sberid_access_token`).
        """
        return _SberIdBearerView(self)

    def set_sberid_tokens(self, tokens: SberIdTokens) -> None:
        """Установить новые SberID-токены (например, после первого OAuth-flow)."""
        self._sberid = tokens
        self._single_flight.reset()  # новые учётные данные — refresh снова возможен
        self._sberid_single_flight.reset()

    def set_companion_tokens(self, tokens: CompanionTokens) -> None:
        """Установить новые companion-токены (после первого обмена)."""
        self._companion = tokens
        self._single_flight.reset()

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

    async def _refresh_sberid_only(self) -> None:
        """Ротировать ТОЛЬКО SberID-токен (без обмена на companion).

        Вызывается через `_sberid_single_flight` для канала настроек. Сам
        обмен на companion не делает — companion-ветка живёт своей жизнью,
        но обе делят `self._sberid`, поэтому ротация здесь видна и там.
        """
        if self._sberid is None:
            raise InvalidGrant("No SberID tokens — full re-auth required")
        if not self._sberid.refresh_token:
            raise InvalidGrant("SberID has no refresh_token — full re-auth required")
        _LOGGER.debug("Rotating SberID tokens (raw bearer channel)")
        self._sberid = await refresh_sberid_tokens(
            self._http,
            self._sberid.refresh_token,
            client_id=self._client_id,
            endpoint=self._token_endpoint,
        )
        await self._notify_sberid_refreshed()

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
        except Exception:
            _LOGGER.exception("on_sberid_refreshed callback failed")


class _SberIdBearerView:
    """Вью на `AuthManager`, отдающий сырой SberID access_token.

    Реализует `AuthManagerProtocol` (`access_token`/`force_refresh`) поверх
    `AuthManager`, но возвращает НЕ companion, а сам SberID-токен — для
    каналов вроде настроек колонок. Своего состояния токенов не держит:
    делегирует в AuthManager, который остаётся единственным владельцем
    ротации SberID. Это устраняет гонку двух независимых refresh'ей за один
    одноразовый refresh_token (симптом: канал настроек «слетал» через время
    после входа через Сбер ID).
    """

    __slots__ = ("_mgr",)

    def __init__(self, mgr: AuthManager) -> None:
        self._mgr = mgr

    async def access_token(self) -> str:
        return await self._mgr.sberid_access_token()

    async def force_refresh(self, stale_token: str | None = None) -> None:
        await self._mgr.force_refresh_sberid(stale_token)
