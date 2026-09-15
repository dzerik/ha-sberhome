"""HttpTransport — обёртка httpx с auth, headers, retry, error mapping.

Это **единственное место** в aiosber, через которое идут все REST-запросы к
gateway. Никакой бизнес-логики, только транспорт + auth.

Ответственности:
- Подписать запрос актуальным companion-токеном (через `AuthManager`).
- Прокинуть обязательные headers (RqUID, x-trace-id, User-Agent, ...).
- На 401 — вызвать `auth.force_refresh()` и сделать ОДИН retry. 403 токен
  не обновляет: у Sber это «эндпоинт недоступен этому аккаунту», а не
  истёкший токен — отдаётся как `ApiError(403)`.
- Замаппить httpx-ошибки и HTTP-статусы в типизированные `aiosber.exceptions`.
- Закрыть httpx.AsyncClient при `aclose()`.

Принцип DI: httpx.AsyncClient инжектится извне (в HA — общий, в тестах — respx).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Final

import httpx

from ..auth.store import AuthManagerProtocol
from ..const import DEFAULT_USER_AGENT, GATEWAY_BASE_URL
from ..exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
    RateLimitError,
)

_LOGGER = logging.getLogger(__name__)


class HttpTransport:
    """Authenticated HTTP transport for gateway/v1/* endpoints.

    Args:
        http: shared httpx.AsyncClient (DI). Желательно с настроенным `verify=` на SSL context.
        auth: `AuthManager` для получения / обновления companion-токена.
        base_url: базовый URL gateway (по умолчанию prod).
        user_agent: значение User-Agent.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        auth: AuthManagerProtocol,
        *,
        base_url: str = GATEWAY_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
        auth_header_name: str = "X-AUTH-jwt",
        auth_header_prefix: str = "",
    ) -> None:
        self._http = http
        self._auth = auth
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent
        # Gateway использует X-AUTH-jwt без префикса; companion-канал настроек
        # колонок — Authorization: Bearer <token>. Одна транспортная логика,
        # различается только имя/префикс auth-заголовка.
        self._auth_header_name = auth_header_name
        self._auth_header_prefix = auth_header_prefix

    # ----- HTTP verbs -----
    async def get(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("DELETE", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> httpx.Response:
        return await self.request("PATCH", path, **kwargs)

    # ----- Core -----
    async def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,  # noqa: ASYNC109 — httpx per-request timeout, не asyncio
    ) -> httpx.Response:
        """Сделать запрос с подписью companion-токеном.

        Retries:
        - **HTTP 401** — force refresh token + повторить запрос. Параллельные
          401 с одним токеном дают один refresh (single-flight в auth).
        - **HTTP 403** — без refresh и retry: `ApiError(403)`.
        - **In-band code 16** (token expired в body 200 OK, без честного 401) —
          force refresh + повторить. Compat-strategy для случаев, когда
          gateway отдаёт code-16 inline.

        Возвращает успешный httpx.Response (status 2xx). На любой 4xx/5xx
        после retry — бросает соответствующее `aiosber.exceptions.*`.
        """
        url = self._url(path)

        resp, used_token = await self._send_with_auth_retry(
            method, url, json=json, params=params, headers=headers, timeout=timeout
        )

        # In-band `code 16` (token expired в JSON-body 200 OK) — Sber иногда
        # отдаёт ошибку через payload вместо HTTP-кода. Делаем повтор как при 401.
        if _is_inband_token_expired(resp):
            _LOGGER.debug(
                "%s %s → 200 with in-band code 16 (token expired); refreshing + retry",
                method,
                url,
            )
            await self._force_refresh(used_token)
            resp, _ = await self._send_with_auth_retry(
                method,
                url,
                json=json,
                params=params,
                headers=headers,
                timeout=timeout,
                skip_auth_retry=True,
            )
            if _is_inband_token_expired(resp):
                raise AuthError("Token expired and inband retry also returned code 16")

        return self._handle_response(resp, method=method, url=url)

    async def _send_with_auth_retry(
        self,
        method: str,
        url: str,
        *,
        json: Any,
        params: dict[str, Any] | None,
        headers: dict[str, str] | None,
        timeout: float | None,  # noqa: ASYNC109 — httpx per-request timeout, не asyncio
        skip_auth_retry: bool = False,
    ) -> tuple[httpx.Response, str]:
        """Один send с опциональным 401 retry. Вынесено чтобы code-16
        path мог дёрнуть refresh+send без повторного auth-retry-цикла.

        Returns:
            Ответ и токен, с которым он получен (нужен code-16 path'у, чтобы
            не обновлять токен, уже заменённый соседним запросом).
        """
        token = await self._auth.access_token()
        attempt_headers = self._build_headers(token, extra=headers)
        try:
            resp = await self._http.request(
                method,
                url,
                json=json,
                params=params,
                headers=attempt_headers,
                timeout=timeout,
            )
        except httpx.TimeoutException as err:
            raise NetworkError(f"Timeout {method} {url}: {err}") from err
        except httpx.ConnectError as err:
            raise NetworkError(f"Connect failed {method} {url}: {err}") from err
        except httpx.HTTPError as err:
            raise NetworkError(f"HTTP error {method} {url}: {err}") from err

        # Только 401: 403 у Sber — «эндпоинт недоступен аккаунту», refresh
        # его не лечит, а лишь гоняет обмен токенов и запись config entry.
        if not skip_auth_retry and resp.status_code == 401:
            _LOGGER.debug(
                "%s %s → %s; refreshing token and retrying once",
                method,
                url,
                resp.status_code,
            )
            await self._force_refresh(token)

            token = await self._auth.access_token()
            retry_headers = self._build_headers(token, extra=headers)
            try:
                resp = await self._http.request(
                    method,
                    url,
                    json=json,
                    params=params,
                    headers=retry_headers,
                    timeout=timeout,
                )
            except httpx.HTTPError as err:
                raise NetworkError(f"Retry failed {method} {url}: {err}") from err

        return resp, token

    async def _force_refresh(self, stale_token: str) -> None:
        """Обновить токен, отвергнутый сервером (single-flight в auth).

        Raises:
            InvalidGrant: refresh невозможен — нужен reauth.
            AuthError: прочие ошибки refresh (с префиксом «Token refresh failed»).
        """
        try:
            await self._auth.force_refresh(stale_token)
        except InvalidGrant:
            raise
        except AuthError as err:
            raise AuthError(f"Token refresh failed: {err}") from err

    # ----- Lifecycle -----
    async def aclose(self) -> None:
        """Закрыть подлежащий httpx.AsyncClient."""
        await self._http.aclose()

    async def __aenter__(self) -> HttpTransport:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ----- Internal -----
    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return self._base_url + path

    def _build_headers(self, token: str, *, extra: dict[str, str] | None = None) -> dict[str, str]:
        # Gateway требует X-AUTH-jwt (без префикса Bearer). Это отличие от
        # стандартного OAuth2 — Sber использует custom-header для companion-токена.
        # Companion settings-канал переопределяет имя на Authorization + "Bearer ".
        headers = {
            self._auth_header_name: f"{self._auth_header_prefix}{token}",
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "x-trace-id": str(uuid.uuid4()),
        }
        if extra:
            headers.update(extra)
        return headers

    def _handle_response(self, resp: httpx.Response, *, method: str, url: str) -> httpx.Response:
        """Маппинг HTTP статусов в типизированные исключения."""
        if 200 <= resp.status_code < 300:
            return resp

        payload = _safe_json(resp)

        if resp.status_code == 401:
            # Сюда попадаем если retry тоже отдал 401 — значит токен реально невалиден
            raise AuthError(f"Unauthorized after refresh: {method} {url}")
        # 403 (доступ к эндпоинту запрещён) — обычный ApiError ниже: вызывающие
        # (опросы coordinator'а) считают его «не поддерживается», а не reauth.

        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After")
            try:
                retry_after_s = float(retry_after) if retry_after else None
            except ValueError:
                retry_after_s = None
            raise RateLimitError(
                message=str(payload or resp.text[:200] or "rate limited"),
                retry_after=retry_after_s,
                payload=payload,
            )

        message = ""
        code: int | str | None = None
        if payload:
            message = str(payload.get("message") or payload.get("error") or "")
            code = payload.get("code")
        if not message:
            message = resp.text[:200] or f"{method} {url}"

        raise ApiError(resp.status_code, message=message, code=code, payload=payload)


# Gateway in-band error code: token expired. Sber иногда отдаёт его в
# теле 200-OK ответа вместо честного 401 HTTP-кода.
_CODE_TOKEN_EXPIRED: Final[int] = 16


def _is_inband_token_expired(resp: httpx.Response) -> bool:
    """True если 200 OK содержит `{"code": 16}` в JSON-body."""
    if resp.status_code != 200:
        return False
    data = _safe_json(resp)
    if data is None:
        return False
    return data.get("code") == _CODE_TOKEN_EXPIRED


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except ValueError:
        return None
