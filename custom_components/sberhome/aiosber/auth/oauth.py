"""Token exchange и refresh для id.sber.ru.

Все функции принимают `httpx.AsyncClient` через DI — для тестов на respx.
HTTP-обработка вынесена сюда, бизнес-логика (когда refresh, кеш) — в AuthManager.

Все эндпоинты ждут `RqUID` UUID-заголовок. Без него возвращают ошибку.
"""

from __future__ import annotations

import uuid
from typing import Any

import httpx

from ..const import DEFAULT_CLIENT_ID, DEFAULT_REDIRECT_URI, TOKEN_ENDPOINT
from ..exceptions import ApiError, AuthError, InvalidGrant, NetworkError
from .tokens import SberIdTokens


def _new_rquid() -> str:
    """Сгенерировать UUID для заголовка RqUID. Sber ID требует на каждый запрос."""
    return str(uuid.uuid4())


async def exchange_code_for_tokens(
    http: httpx.AsyncClient,
    code: str,
    code_verifier: str,
    *,
    client_id: str = DEFAULT_CLIENT_ID,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    endpoint: str = TOKEN_ENDPOINT,
    rquid: str | None = None,
) -> SberIdTokens:
    """Step 2 OAuth: обменять authorization_code на SberID токены.

    POST endpoint x-www-form-urlencoded + RqUID header.
    """
    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    return await _post_token(http, endpoint, payload, rquid=rquid)


async def refresh_sberid_tokens(
    http: httpx.AsyncClient,
    refresh_token: str,
    *,
    client_id: str = DEFAULT_CLIENT_ID,
    endpoint: str = TOKEN_ENDPOINT,
    rquid: str | None = None,
) -> SberIdTokens:
    """Refresh SberID токенов через `grant_type=refresh_token`."""
    payload = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    return await _post_token(http, endpoint, payload, rquid=rquid)


async def _post_token(
    http: httpx.AsyncClient,
    endpoint: str,
    data: dict[str, Any],
    *,
    rquid: str | None = None,
) -> SberIdTokens:
    """Общая POST-логика token endpoint с маппингом ошибок."""
    headers = {
        "RqUID": rquid or _new_rquid(),
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    try:
        resp = await http.post(endpoint, data=data, headers=headers)
    except httpx.ConnectError as err:
        raise NetworkError(f"Failed to reach {endpoint}: {err}") from err
    except httpx.TimeoutException as err:
        raise NetworkError(f"Timeout contacting {endpoint}: {err}") from err
    except httpx.HTTPError as err:
        raise NetworkError(f"HTTP error contacting {endpoint}: {err}") from err

    return _parse_token_response(resp, grant=data.get("grant_type", ""))


def _parse_token_response(resp: httpx.Response, *, grant: str) -> SberIdTokens:
    """Распарсить response, маппнуть ошибки в типизированные exceptions."""
    if resp.status_code == 200:
        try:
            payload = resp.json()
        except ValueError as err:
            raise AuthError(f"Token endpoint returned non-JSON: {err}") from err
        if "access_token" not in payload:
            raise AuthError(f"Token response missing access_token: {payload}")
        return SberIdTokens.from_dict(payload)

    # Ошибки
    payload = _safe_json(resp)
    error_code = payload.get("error") if payload else None
    error_desc = payload.get("error_description") if payload else resp.text[:200]

    if resp.status_code in (400, 401):
        # OAuth2 spec — invalid_grant означает истёкший / отозванный refresh
        if error_code == "invalid_grant":
            raise InvalidGrant(f"{grant} rejected: {error_desc}")
        raise AuthError(f"OAuth error ({resp.status_code} {error_code}): {error_desc}")
    raise ApiError(
        resp.status_code,
        message=str(error_desc or "token endpoint failed"),
        code=error_code,
        payload=payload,
    )


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except ValueError:
        return None
