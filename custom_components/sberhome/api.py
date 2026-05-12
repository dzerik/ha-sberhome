"""SberAPI shim для config_flow + shared SSL provider.

PR #6 (v5.0.0): HomeAPI оболочка удалена. AuthManager + HttpTransport
теперь строятся напрямую в `__init__.py:async_setup_entry` и инжектятся
в coordinator. Этот модуль остался только ради:

- `SberAPI` — PKCE OAuth-flow для config_flow (создание SberID токенов).
- `async_init_ssl` — shared SslContextProvider в hass.data.

Никакой business-логики здесь нет — она в aiosber.
"""

from __future__ import annotations

import ssl

import httpx

from .aiosber.auth import (
    PkceParams,
    SberIdTokens,
    build_authorize_url,
    exchange_code_for_tokens,
    extract_code_from_redirect,
)
from .aiosber.const import DEFAULT_PARTNER_NAME
from .aiosber.exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
    PkceError,
)
from .aiosber.transport import SslContextProvider
from .const import DOMAIN, LOGGER

REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Ключ в hass.data для shared SslContextProvider — один на HA instance,
# чтобы `ssl.create_default_context()` (~50-200 мс блокирующий I/O)
# выполнялся только один раз.
_SSL_PROVIDER_KEY = f"{DOMAIN}_ssl_provider"


async def async_init_ssl(hass) -> ssl.SSLContext:
    """Инициализировать и вернуть shared SSL context.

    Использует DI-friendly `SslContextProvider` из aiosber (правильный
    async-паттерн с asyncio.Lock + executor'ом). Provider хранится в
    `hass.data` — один на HA instance, чтобы два config entries (если
    такое возможно) не создавали дубль контекста.
    """
    provider: SslContextProvider = hass.data.get(_SSL_PROVIDER_KEY)
    if provider is None:
        provider = SslContextProvider()
        hass.data[_SSL_PROVIDER_KEY] = provider
    return await provider.get()


def _normalize_legacy_token(token: dict) -> dict:
    """Сконвертить authlib-стиль `expires_at` в aiosber-стиль `obtained_at`.

    Legacy entries (≤ 2.5.x) хранят токен в формате authlib OAuth2Token, где
    `expires_at` — абсолютное время истечения. SberIdTokens хочет `obtained_at`
    (момент получения). Переводим: obtained_at = expires_at - expires_in.
    """
    if "obtained_at" in token or "expires_at" not in token:
        return token
    expires_in = int(token.get("expires_in", 3600))
    return {**token, "obtained_at": token["expires_at"] - expires_in}


class SberAPI:
    """OAuth2 PKCE-shim для config_flow.

    Хранит SberID-токены. Companion-токены живут в AuthManager (передаётся
    в coordinator из `__init__.py:async_setup_entry`), чтобы не дублировать
    состояние.

    Args:
        token: сохранённый SberID token dict (из config_entry.data); или None
            для свежего OAuth flow.
        http: pre-built httpx.AsyncClient (DI). Если None — создаётся свой
            клиент с дефолтным SSL (только для CLI/unit-тестов; HA всегда
            передаёт shared).
        owns_http: True если клиент создан внутри и должен быть закрыт в
            `aclose()`. False — когда http инжектирован снаружи (закрывать
            должен caller).
    """

    def __init__(
        self,
        token: dict | None = None,
        *,
        http: httpx.AsyncClient | None = None,
        owns_http: bool | None = None,
    ) -> None:
        self._sberid: SberIdTokens | None = (
            SberIdTokens.from_dict(_normalize_legacy_token(token)) if token else None
        )
        self._pkce: PkceParams | None = None
        if http is not None:
            self._http = http
            # Явный owns_http для DI: config_flow передаёт owns_http=True
            # (httpx для OAuth живёт только внутри flow),
            # __init__.py передаёт owns_http=False (shared пул закрывает
            # coordinator.async_shutdown).
            self._owns_http = bool(owns_http) if owns_http is not None else False
        else:
            # Fallback для CLI/тестов: создаём свой клиент с дефолтным SSL
            # контекстом (без Russian Trusted Root CA — это только для тестов).
            self._http = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
            self._owns_http = True

    @property
    def token(self) -> dict | None:
        """Текущий SberID-токен в JSON-сериализуемой форме (для config_entry.data)."""
        return self._sberid.to_dict() if self._sberid else None

    @property
    def sberid_tokens(self) -> SberIdTokens | None:
        """Прямой доступ к SberIdTokens — для передачи в AuthManager."""
        return self._sberid

    def create_authorization_url(self) -> str:
        """Сгенерировать PKCE и вернуть URL Sber ID для редиректа."""
        self._pkce = PkceParams.generate()
        return build_authorize_url(self._pkce, partner_name=DEFAULT_PARTNER_NAME)

    async def authorize_by_url(self, url: str) -> bool:
        """Извлечь code из callback URL, обменять на SberID токены.

        Returns True при успехе, False при любой auth/network/pkce ошибке.
        """
        if self._pkce is None:
            LOGGER.debug("authorize_by_url called without prior create_authorization_url")
            return False
        try:
            code = extract_code_from_redirect(url, expected_state=self._pkce.state)
            tokens = await exchange_code_for_tokens(
                self._http, code, code_verifier=self._pkce.verifier
            )
        except (PkceError, AuthError, InvalidGrant, NetworkError, ApiError):
            LOGGER.debug("OAuth token exchange failed", exc_info=True)
            return False
        self._sberid = tokens
        return True

    async def aclose(self) -> None:
        """Закрыть внутренний httpx если он был создан внутри.

        При DI-инжекции (http=...) клиент НЕ закрывается — owner его
        снаружи (`__init__.py::async_unload_entry`).
        """
        if self._owns_http:
            await self._http.aclose()


