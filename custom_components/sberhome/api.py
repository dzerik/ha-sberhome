"""HA-shim над aiosber.

Тонкие обёртки `SberAPI` и `HomeAPI` сохраняют легаси-интерфейс для
config_flow.py и платформ (entity._async_send_bundle), внутри полностью
делегируют работу типизированному стеку `aiosber/`:

- `SberAPI` хранит SberID-токены и делает PKCE-флоу (config_flow).
- `HomeAPI` владеет AuthManager + HttpTransport, кеширует raw devices в
  `_cached_devices` для совместимости с WS-патчем (coordinator) и
  diagnostics, выполняет команды через `transport.put`, мапит aiosber
  исключения в SberSmartHome иерархию.

Никакой business-логики здесь нет — она в aiosber.
"""

from __future__ import annotations

import asyncio
import ssl
from datetime import UTC, datetime
from typing import Any

import httpx

from .aiosber.auth import (
    AuthManager,
    InMemoryTokenStore,
    PkceParams,
    SberIdTokens,
    TokenStore,
    build_authorize_url,
    exchange_code_for_tokens,
    extract_code_from_redirect,
)
from .aiosber.auth.manager import SberIdRefreshCallback
from .aiosber.const import DEFAULT_PARTNER_NAME
from .aiosber.dto.device import DeviceDto
from .aiosber.dto.union import UnionTreeDto
from .aiosber.exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
    PkceError,
    RateLimitError,
)
from .aiosber.transport import HttpTransport, SslContextProvider
from .const import DOMAIN, LOGGER
from .exceptions import SberApiError, SberAuthError, SberConnectionError
from .utils import extract_devices

REQUEST_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
COMMAND_RETRY_DELAY = 1.0

# In-band gateway error codes
_CODE_TOKEN_EXPIRED = 16

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

    Хранит SberID-токены. Companion-токены живут в HomeAPI (через AuthManager),
    чтобы не дублировать состояние.

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
        """Прямой доступ к SberIdTokens — для передачи в HomeAPI/AuthManager."""
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


class HomeAPI:
    """HA-shim над aiosber HttpTransport + AuthManager.

    Сохраняет атрибут `_cached_devices: dict[str, dict]` в raw виде — это нужно
    для:
    - точечного WS-патча (`coordinator._on_ws_device_state` мутирует raw dict);
    - diagnostics, который сериализует raw dict в JSON;
    - sbermap, который lazy-конвертит в DeviceDto через `get_cached_devices_dto`.
    """

    def __init__(
        self,
        sber: SberAPI,
        *,
        http: httpx.AsyncClient | None = None,
        token_store: TokenStore | None = None,
        on_sberid_refreshed: SberIdRefreshCallback | None = None,
    ) -> None:
        self._sber = sber
        if http is not None:
            self._http = http
            self._owns_http = False
        else:
            # Fallback для CLI/тестов (SSL без Russian Trusted Root CA).
            self._http = httpx.AsyncClient(timeout=REQUEST_TIMEOUT)
            self._owns_http = True
        # Companion-токены: по умолчанию in-memory (для unit-тестов / CLI),
        # HA-адаптер прокидывает HATokenStore, который пишет в
        # config_entry.data, чтобы токены переживали рестарт.
        self._store = token_store or InMemoryTokenStore()
        self._auth = AuthManager(
            http=self._http,
            store=self._store,
            sberid_tokens=sber.sberid_tokens,
            on_sberid_refreshed=on_sberid_refreshed,
        )
        self._transport = HttpTransport(http=self._http, auth=self._auth)
        self._cached_devices: dict = {}
        self._cached_tree: UnionTreeDto | None = None

    async def get_auth_manager(self) -> AuthManager:
        """Доступ к AuthManager для WS handshake (`coordinator._run_ws`).

        Async по контракту с coordinator (он awaits): даёт возможность
        в будущем lazy-инициализировать AuthManager без breaking-change.
        """
        return self._auth

    def get_cached_devices_dto(self) -> dict[str, DeviceDto]:
        """Lazy-конверт raw → DeviceDto для sbermap.

        Resilient: skip + log devices которые не парсятся, чтобы один
        нестандартный device не валил polling всем остальным.
        """
        out: dict[str, DeviceDto] = {}
        for device_id, raw in self._cached_devices.items():
            try:
                dto = DeviceDto.from_dict(raw)
            except Exception:  # noqa: BLE001
                LOGGER.debug(
                    "Cannot parse DTO for device %s — skipping",
                    device_id,
                    exc_info=True,
                )
                continue
            if dto is not None:
                out[device_id] = dto
        return out

    async def update_devices_cache(self) -> None:
        device_data = await self._request("GET", "/device_groups/tree")
        raw_tree = device_data["result"]
        self._cached_devices = extract_devices(raw_tree)
        # Параллельно парсим typed tree для StateCache.
        self._cached_tree = UnionTreeDto.from_dict(raw_tree)

    def get_cached_tree(self) -> UnionTreeDto | None:
        """Typed дерево групп — для StateCache."""
        return self._cached_tree

    def get_cached_devices(self) -> dict:
        return self._cached_devices

    def get_cached_device(self, device_id: str) -> dict:
        return self._cached_devices[device_id]

    async def fetch_device(self, device_id: str) -> dict:
        """GET /devices/{id} — individual device fetch.

        Альтернатива batch `/device_groups/tree` (который для c2c-устройств
        может отдавать stale values). Мобильное приложение Sber использует
        именно этот endpoint для single-device detail view.
        """
        data = await self._request("GET", f"/devices/{device_id}")
        return data.get("result") or data

    async def set_device_state(self, device_id: str, state: list[dict]) -> None:
        """Set device state via the gateway API with one network-retry."""
        try:
            await self._set_device_state_inner(device_id, state)
        except SberConnectionError:
            LOGGER.debug(
                "Command failed for %s, retrying in %ss",
                device_id,
                COMMAND_RETRY_DELAY,
            )
            await asyncio.sleep(COMMAND_RETRY_DELAY)
            await self._set_device_state_inner(device_id, state)

    async def _set_device_state_inner(self, device_id: str, state: list[dict]) -> None:
        """Send device state update + merge into local cache."""
        await self._request(
            "PUT",
            f"/devices/{device_id}/state",
            json={
                "device_id": device_id,
                "desired_state": state,
                "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            },
        )

        if device_id in self._cached_devices:
            for state_val in state:
                for attribute in self._cached_devices[device_id]["desired_state"]:
                    if attribute["key"] == state_val["key"]:
                        attribute.update(state_val)
                        break

    async def _request(self, method: str, path: str, *, json: Any = None) -> dict:
        """Низкоуровневый запрос: маппинг aiosber → SberSmartHome исключений.

        Дополнительно ловит in-band `code 16` (token expired): force_refresh +
        retry один раз. Это compat-strategy для случаев, когда gateway отдаёт
        200 OK с code-16 вместо честного 401.
        """
        payload = await self._request_once(method, path, json=json)

        if isinstance(payload, dict) and payload.get("code") == _CODE_TOKEN_EXPIRED:
            LOGGER.debug("Gateway code 16 (token expired) — force refresh + retry")
            try:
                await self._auth.force_refresh()
            except (AuthError, InvalidGrant) as err:
                raise SberAuthError(str(err)) from err
            payload = await self._request_once(method, path, json=json)
            if isinstance(payload, dict) and payload.get("code") == _CODE_TOKEN_EXPIRED:
                raise SberAuthError("Token expired and retry failed")

        return payload

    async def _request_once(self, method: str, path: str, *, json: Any = None) -> dict:
        try:
            resp = await self._transport.request(method, path, json=json)
        except (AuthError, InvalidGrant) as err:
            raise SberAuthError(str(err)) from err
        except RateLimitError as err:
            retry_after = int(err.retry_after) if err.retry_after else 60
            LOGGER.warning("API rate limited, retry after %ds", retry_after)
            raise SberApiError(
                code=429,
                status_code=429,
                message=str(err),
                retry_after=retry_after,
            ) from err
        except NetworkError as err:
            raise SberConnectionError(f"Connection error: {err}") from err
        except ApiError as err:
            code = err.code if isinstance(err.code, int) else -1
            raise SberApiError(
                code=code, status_code=err.status_code, message=err.message or str(err)
            ) from err

        try:
            return resp.json()
        except (ValueError, TypeError) as err:
            raise SberApiError(
                code=-1, status_code=resp.status_code, message=resp.text[:200]
            ) from err

    async def aclose(self) -> None:
        """Закрыть transport, плюс httpx если он был создан внутри.

        При DI-инжекции (http=...) httpx закрывает owner снаружи.
        """
        if self._owns_http:
            await self._transport.aclose()
