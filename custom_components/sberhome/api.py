"""HA-side adapter над `aiosber.SberClient`.

Сохраняет публичный интерфейс старых `SberAPI`/`HomeAPI` (для совместимости
с платформами и тестами), но всю работу делегирует в `aiosber/`.

Старая реализация `api.py` (authlib + global SSL context + JWT exp parser +
manual retry) ушла. Теперь:
- Аутентификация — `aiosber.auth` (PKCE + AuthManager + InMemoryTokenStore).
- Транспорт — `aiosber.transport.HttpTransport` (httpx + retry + headers).
- API endpoints — `aiosber.api.DeviceAPI` (через `SberClient`).
- SSL — `aiosber.transport.SslContextProvider` (lazy executor, no global state).

Это **тонкий адаптер**, постепенно заменится прямыми вызовами `SberClient`
(см. CLAUDE.md → "Архитектурная парадигма" → roadmap).
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from homeassistant.core import HomeAssistant

from .aiosber import (
    AttributeValueDto,
    AttributeValueType,
    SberClient,
)
from .aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
    PkceParams,
    SberIdTokens,
    TokenStore,
    build_authorize_url,
    exchange_code_for_tokens,
    exchange_for_companion_token,
    extract_code_from_redirect,
)
from .aiosber.const import COMPANION_BASE_URL, COMPANION_TOKEN_PATH, DEFAULT_REDIRECT_URI
from .aiosber.exceptions import (
    ApiError as AioApiError,
)
from .aiosber.exceptions import (
    AuthError as AioAuthError,
)
from .aiosber.exceptions import (
    InvalidGrant,
)
from .aiosber.exceptions import (
    NetworkError as AioNetworkError,
)
from .aiosber.exceptions import (
    RateLimitError as AioRateLimitError,
)
from .aiosber.transport import HttpTransport, SslContextProvider
from .aiosber.transport.http import _safe_json
from .const import LOGGER
from .exceptions import SberApiError, SberAuthError, SberConnectionError
from .utils import extract_devices

COMMAND_RETRY_DELAY = 1.0


# Один shared SslContextProvider на процесс — экономим один build SSL-контекста.
# Не нарушает правило "no global state в aiosber/" — этот файл — HA-side adapter,
# здесь HA-уровень глобальности (один HA-процесс) допустим.
_ssl_provider = SslContextProvider()


async def async_init_ssl(hass: HomeAssistant) -> None:
    """Pre-warm SSL context in executor (non-blocking).

    Сохраняем сигнатуру для совместимости с `__init__.py`/`config_flow.py`.
    """
    await _ssl_provider.get()


# =============================================================================
# SberAPI shim — управление токенами (PKCE + companion exchange)
# =============================================================================
class SberAPI:
    """OAuth2 PKCE client для авторизации в Sber ID + companion exchange.

    Публичный интерфейс совместим со старой реализацией:
    - `__init__(token=None)` — создать пустой (для нового OAuth) или восстановить
      из сохранённого token dict.
    - `token` (property) — token dict для сериализации в config_entry.
    - `create_authorization_url()` — URL для редиректа на id.sber.ru.
    - `authorize_by_url(url)` — обмен code на SberID токены.
    - `fetch_home_token()` — обмен SberID на companion token.
    - `aclose()` — закрыть HTTP-клиент.
    """

    def __init__(self, token: dict | None = None) -> None:
        self._http: httpx.AsyncClient | None = None  # lazy-init после first use (нужен SSL)
        self._pkce: PkceParams | None = None  # генерируется при create_authorization_url
        self._sberid: SberIdTokens | None = (
            SberIdTokens.from_dict(token) if token else None
        )
        self._companion: CompanionTokens | None = None

    @property
    def token(self) -> dict | None:
        """Возвращает dict для сохранения в config_entry.data."""
        if self._sberid is None:
            return None
        return self._sberid.to_dict()

    async def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None:
            ssl_ctx = await _ssl_provider.get()
            self._http = httpx.AsyncClient(verify=ssl_ctx)
        return self._http

    def create_authorization_url(self) -> str:
        """Сгенерировать PKCE-параметры и URL для редиректа на id.sber.ru."""
        self._pkce = PkceParams.generate()
        return build_authorize_url(self._pkce, redirect_uri=DEFAULT_REDIRECT_URI)

    async def authorize_by_url(self, url: str) -> bool:
        """Обмен authorization_code из callback URL на SberID токены.

        Args:
            url: callback URL вида `companionapp://host?code=...&state=...`.

        Returns:
            True если успех, False иначе (для совместимости со старым API).
        """
        if self._pkce is None:
            LOGGER.debug("authorize_by_url called without create_authorization_url first")
            return False
        try:
            code = extract_code_from_redirect(url, expected_state=self._pkce.state)
        except Exception:
            LOGGER.debug("Failed to extract code from redirect URL", exc_info=True)
            return False
        try:
            http = await self._ensure_http()
            self._sberid = await exchange_code_for_tokens(
                http,
                code,
                self._pkce.verifier,
                redirect_uri=DEFAULT_REDIRECT_URI,
            )
            return True
        except Exception:
            LOGGER.debug("OAuth token exchange failed", exc_info=True)
            return False

    async def fetch_home_token(self) -> str:
        """Exchange SberID access_token for companion token. Returns token string.

        Маппит aiosber-исключения в legacy `SberAuthError` / `SberConnectionError`.
        """
        if self._sberid is None:
            raise SberAuthError("No SberID tokens — authorize first")
        try:
            http = await self._ensure_http()
            tokens = await exchange_for_companion_token(
                http,
                self._sberid.access_token,
                endpoint=COMPANION_BASE_URL + COMPANION_TOKEN_PATH,
            )
            self._companion = tokens
            return tokens.access_token
        except AioAuthError as err:
            raise SberAuthError(str(err)) from err
        except AioNetworkError as err:
            raise SberConnectionError(str(err)) from err
        except Exception as err:
            LOGGER.debug("Failed to fetch home token", exc_info=True)
            raise SberAuthError(f"Failed to fetch home token: {err}") from err

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None


# =============================================================================
# HomeAPI shim — операции с устройствами через SberClient
# =============================================================================
class HomeAPI:
    """Adapter над `SberClient.devices` с device cache + legacy интерфейс.

    Публичный интерфейс совместим со старой реализацией:
    - `update_token()` — refresh companion token (no-op если валиден).
    - `request(method, url, retry=True, **kwargs) -> dict` — низкоуровневый запрос.
    - `get_device_tree() -> dict` — устройства как dict (через extract_devices).
    - `update_devices_cache()` / `get_cached_devices()` / `get_cached_device(id)`.
    - `set_device_state(device_id, state)` — команда устройству с retry.
    - `aclose()`.
    """

    def __init__(self, sber: SberAPI, *, token_store: TokenStore | None = None) -> None:
        """Init HomeAPI.

        Args:
            sber: SberAPI с уже полученными SberID-токенами.
            token_store: persistent storage для companion-токенов (опционально).
                По умолчанию `InMemoryTokenStore` (теряется при перезапуске).
                HA-side подаёт `HATokenStore` чтобы persist между restarts.
        """
        self._sber = sber
        self._token_store: TokenStore = token_store or InMemoryTokenStore()
        # Lazy: Создаются при первом запросе, когда уже есть companion token.
        self._http: httpx.AsyncClient | None = None
        self._auth_mgr: AuthManager | None = None
        self._transport: HttpTransport | None = None
        self._client: SberClient | None = None
        self._cached_devices: dict = {}

    async def _ensure_client(self) -> SberClient:
        """Lazy-init SberClient.

        Поток:
        1. Сначала пытаемся загрузить сохранённый companion из token_store.
        2. Если нет / истёк — берём через `_sber.fetch_home_token()` (companion exchange).
        3. Сохраняем в token_store для следующего запуска.
        """
        if self._client is not None:
            return self._client

        # Step 1: попытка load из persistent store (HATokenStore сохраняет в config_entry).
        if self._sber._companion is None:
            stored = await self._token_store.load()
            if stored is not None and not stored.is_expired(leeway=60):
                self._sber._companion = stored

        # Step 2: если по-прежнему нет — fetch новый.
        if self._sber._companion is None:
            await self._sber.fetch_home_token()
        assert self._sber._companion is not None

        # Step 3: сохранить в store (для следующего HA-restart'а).
        await self._token_store.save(self._sber._companion)

        # Setup SberClient с persistent store — AuthManager будет save() при refresh.
        self._http = await self._sber._ensure_http()
        # Используем переданный token_store вместо InMemoryTokenStore!
        # Так AuthManager.force_refresh() автоматически persist'ит новый токен.
        self._auth_mgr = AuthManager(
            http=self._http,
            store=self._token_store,
            sberid_tokens=self._sber._sberid,
        )
        self._auth_mgr.set_companion_tokens(self._sber._companion)
        self._transport = HttpTransport(http=self._http, auth=self._auth_mgr)
        self._client = SberClient(transport=self._transport)
        return self._client

    async def update_token(self) -> None:
        """Refresh companion token if expired."""
        client = await self._ensure_client()
        # AuthManager сам разберётся, нужен ли refresh.
        await client.transport._auth.access_token()

    async def get_auth_manager(self) -> AuthManager:
        """Return the underlying `AuthManager` (для WebSocketClient).

        Lazy-инициализирует SberClient если ещё не было запросов.
        """
        client = await self._ensure_client()
        return client.transport._auth

    async def get_sber_client(self) -> SberClient:
        """Return the underlying `SberClient` (для прямых вызовов API)."""
        return await self._ensure_client()

    async def request(
        self, method: str, url: str, retry: bool = True, **kwargs
    ) -> dict:
        """Low-level authenticated request. Возвращает распарсенный JSON."""
        client = await self._ensure_client()
        try:
            resp = await client.transport.request(method, url, **kwargs)
        except AioRateLimitError as err:
            raise SberApiError(
                code=429,
                status_code=429,
                message=f"Rate limited, retry after {err.retry_after or 60}s",
                retry_after=int(err.retry_after or 60),
            ) from err
        except InvalidGrant as err:
            raise SberAuthError(f"Token expired and refresh failed: {err}") from err
        except AioAuthError as err:
            raise SberAuthError(str(err)) from err
        except AioApiError as err:
            raise SberApiError(
                code=int(err.code) if isinstance(err.code, int) else -1,
                status_code=err.status_code,
                message=str(err.message or err),
            ) from err
        except AioNetworkError as err:
            raise SberConnectionError(str(err)) from err

        try:
            return resp.json()
        except ValueError as err:
            raise SberApiError(
                code=-1, status_code=resp.status_code, message="Invalid JSON response"
            ) from err

    async def get_device_tree(self) -> dict:
        """GET /device_groups/tree — корневое дерево с устройствами и группами."""
        return (await self.request("GET", "/device_groups/tree"))["result"]

    async def update_devices_cache(self) -> None:
        device_data = await self.get_device_tree()
        self._cached_devices = extract_devices(device_data)

    def get_cached_devices(self) -> dict:
        return self._cached_devices

    def get_cached_device(self, device_id: str) -> dict:
        return self._cached_devices[device_id]

    def get_cached_devices_dto(self) -> dict[str, Any]:
        """Same data as get_cached_devices(), но typed: dict[str, DeviceDto].

        Lazy-converts raw dicts → DeviceDto via aiosber.dto.from_dict. Используется
        coordinator'ом + sbermap для построения кэша HaEntityData.
        """
        from .aiosber.dto.device import DeviceDto

        out: dict[str, Any] = {}
        for device_id, raw in self._cached_devices.items():
            dto = DeviceDto.from_dict(raw)
            if dto is not None:
                out[device_id] = dto
        return out

    async def set_device_state(
        self, device_id: str, state: list[dict]
    ) -> None:
        """Set device state with one retry on connection error."""
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

    async def _set_device_state_inner(
        self, device_id: str, state: list[dict]
    ) -> None:
        """Send PUT /devices/{id}/state via aiosber DeviceAPI."""
        client = await self._ensure_client()
        # Конвертируем legacy list[dict] → list[AttributeValueDto].
        attrs = [_legacy_state_to_attr(item) for item in state]
        try:
            await client.devices.set_state(device_id, attrs)
        except AioRateLimitError as err:
            raise SberApiError(
                code=429,
                status_code=429,
                message=f"Rate limited, retry after {err.retry_after or 60}s",
                retry_after=int(err.retry_after or 60),
            ) from err
        except AioAuthError as err:
            raise SberAuthError(str(err)) from err
        except AioApiError as err:
            raise SberApiError(
                code=int(err.code) if isinstance(err.code, int) else -1,
                status_code=err.status_code,
                message=str(err.message or err),
            ) from err
        except AioNetworkError as err:
            raise SberConnectionError(str(err)) from err

        # Merge into local cache (как делал старый код).
        if device_id in self._cached_devices:
            for state_val in state:
                for attribute in self._cached_devices[device_id]["desired_state"]:
                    if attribute["key"] == state_val["key"]:
                        attribute.update(state_val)
                        break

    async def aclose(self) -> None:
        """Close underlying client. Safe to call multiple times."""
        # Internal _http принадлежит SberAPI — не закрываем здесь дважды.
        # SberClient/transport закрытие сделают свой aclose() который закроет http.
        # Чтобы не двойного-закрыть, помечаем что мы owned httpx.
        # Старая семантика: HomeAPI владел отдельным httpx.AsyncClient.
        # Сейчас мы переиспользуем SberAPI._http (он сам закроется).
        # Поэтому здесь — no-op для http, только сбросить ссылки.
        self._client = None
        self._transport = None
        self._auth_mgr = None
        self._http = None  # SberAPI закроет


# =============================================================================
# Helpers
# =============================================================================
def _legacy_state_to_attr(item: dict[str, Any]) -> AttributeValueDto:
    """Convert legacy `{"key": ..., "X_value": ...}` dict → AttributeValueDto.

    Старые HA-платформы шлют такие dict'ы. Тип определяется по тому,
    какое поле `*_value` присутствует.
    """
    key = item.get("key", "")
    if "bool_value" in item:
        return AttributeValueDto(
            key=key, type=AttributeValueType.BOOL, bool_value=item["bool_value"]
        )
    if "integer_value" in item:
        return AttributeValueDto(
            key=key,
            type=AttributeValueType.INTEGER,
            integer_value=int(item["integer_value"]),
        )
    if "float_value" in item:
        return AttributeValueDto(
            key=key, type=AttributeValueType.FLOAT, float_value=float(item["float_value"])
        )
    if "string_value" in item:
        return AttributeValueDto(
            key=key, type=AttributeValueType.STRING, string_value=str(item["string_value"])
        )
    if "enum_value" in item:
        return AttributeValueDto(
            key=key, type=AttributeValueType.ENUM, enum_value=item["enum_value"]
        )
    if "color_value" in item:
        from .aiosber import ColorValue

        cv_raw = item["color_value"]
        # Поддержка двух форматов:
        # legacy {h, s, v} → reverse-engineered correct {hue, saturation, brightness}
        if "hue" in cv_raw:
            cv = ColorValue(
                hue=int(cv_raw["hue"]),
                saturation=int(cv_raw["saturation"]),
                brightness=int(cv_raw["brightness"]),
            )
        else:
            cv = ColorValue(
                hue=int(cv_raw.get("h", 0)),
                saturation=int(cv_raw.get("s", 0)),
                brightness=int(cv_raw.get("v", 0)),
            )
        return AttributeValueDto(key=key, type=AttributeValueType.COLOR, color_value=cv)
    # fallback — пустой
    return AttributeValueDto(key=key)


# Re-export для legacy-совместимости с тестами импортирующими из api.py
__all__ = [
    "COMMAND_RETRY_DELAY",
    "HomeAPI",
    "SberAPI",
    "async_init_ssl",
]


def _parse_jwt_exp(token: str) -> float | None:
    """Legacy JWT exp parser (deprecated).

    Сохранён для совместимости со старыми тестами, но не используется внутри
    нового HomeAPI — refresh теперь полностью через AuthManager.
    """
    import base64
    import json as _json

    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        data = _json.loads(base64.urlsafe_b64decode(payload))
        return data.get("exp")
    except Exception:
        return None


# Re-export _safe_json for some tests that may use it
_ = _safe_json  # avoid unused-import warning
