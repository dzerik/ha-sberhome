"""HttpTransport — обёртка httpx с auth, headers, retry, error mapping.

Это **единственное место** в aiosber, через которое идут все REST-запросы к
gateway. Никакой бизнес-логики, только транспорт + auth.

Ответственности:
- Подписать запрос актуальным companion-токеном (через `AuthManager`).
- Прокинуть обязательные headers (RqUID, x-trace-id, User-Agent, ...).
- На 401/403 — вызвать `auth.force_refresh()` и сделать ОДИН retry.
- Замаппить httpx-ошибки и HTTP-статусы в типизированные `aiosber.exceptions`.
- Закрыть httpx.AsyncClient при `aclose()`.

Принцип DI: httpx.AsyncClient инжектится извне (в HA — общий, в тестах — respx).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

import httpx

from ..auth.manager import AuthManager
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
        auth: AuthManager,
        *,
        base_url: str = GATEWAY_BASE_URL,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self._http = http
        self._auth = auth
        self._base_url = base_url.rstrip("/")
        self._user_agent = user_agent

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
        timeout: float | None = None,
    ) -> httpx.Response:
        """Сделать запрос с подписью companion-токеном и retry на 401.

        Возвращает успешный httpx.Response (status 2xx). На любой 4xx/5xx
        бросает соответствующее `aiosber.exceptions.*`.
        """
        url = self._url(path)
        attempt_headers = await self._build_headers(extra=headers)

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

        # 401/403 — попробуем один refresh + retry
        if resp.status_code in (401, 403):
            _LOGGER.debug(
                "%s %s → %s; refreshing token and retrying once",
                method, url, resp.status_code,
            )
            try:
                await self._auth.force_refresh()
            except InvalidGrant:
                # Refresh невозможен — пробрасываем как есть, HA-адаптер инициирует reauth
                raise
            except AuthError as err:
                raise AuthError(f"Token refresh failed: {err}") from err

            retry_headers = await self._build_headers(extra=headers)
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

        return self._handle_response(resp, method=method, url=url)

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

    async def _build_headers(self, *, extra: dict[str, str] | None = None) -> dict[str, str]:
        token = await self._auth.access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "User-Agent": self._user_agent,
            "Accept": "application/json",
            "x-trace-id": str(uuid.uuid4()),
        }
        if extra:
            headers.update(extra)
        return headers

    def _handle_response(
        self, resp: httpx.Response, *, method: str, url: str
    ) -> httpx.Response:
        """Маппинг HTTP статусов в типизированные исключения."""
        if 200 <= resp.status_code < 300:
            return resp

        payload = _safe_json(resp)

        if resp.status_code == 401 or resp.status_code == 403:
            # Сюда попадаем если retry тоже отдал 401 — значит токен реально невалиден
            raise AuthError(f"Unauthorized after refresh: {method} {url}")

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


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except ValueError:
        return None
