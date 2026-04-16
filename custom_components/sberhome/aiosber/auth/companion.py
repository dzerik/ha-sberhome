"""Обмен SberID access_token на companion (smarthome) token.

Endpoint: GET `<companion_base>/smarthome/token` с Bearer SberID + x-trace-id.
Этот companion-токен — то, чем подписываются ВСЕ запросы к gateway.

Реверс APK подтверждает использование `smarthome/token` относительно base URL,
но точный host (staros vs gateway) — окончательно не выяснен. По умолчанию
используем `gateway.iot.sberdevices.ru/smarthome/token`; при необходимости
можно переопределить параметром `endpoint`.
"""

from __future__ import annotations

import uuid

import httpx

from ..const import COMPANION_BASE_URL, COMPANION_TOKEN_PATH
from ..exceptions import ApiError, AuthError, NetworkError
from .tokens import CompanionTokens


def _new_trace_id() -> str:
    return str(uuid.uuid4())


async def exchange_for_companion_token(
    http: httpx.AsyncClient,
    sberid_access_token: str,
    *,
    endpoint: str = COMPANION_BASE_URL + COMPANION_TOKEN_PATH,
    trace_id: str | None = None,
) -> CompanionTokens:
    """Step 3: SberID access → companion token (для gateway/v1/*).

    Args:
        http: shared httpx.AsyncClient.
        sberid_access_token: access_token из `exchange_code_for_tokens()`.
        endpoint: полный URL `/smarthome/token`. Override для тестов / других стендов.
        trace_id: значение x-trace-id (для distributed tracing). По умолчанию — новый UUID.

    Returns:
        CompanionTokens с access_token (для Bearer), опц. refresh_token, expires_in.
    """
    headers = {
        "Authorization": f"Bearer {sberid_access_token}",
        "x-trace-id": trace_id or _new_trace_id(),
        "Accept": "application/json",
    }
    try:
        resp = await http.get(endpoint, headers=headers)
    except httpx.ConnectError as err:
        raise NetworkError(f"Failed to reach {endpoint}: {err}") from err
    except httpx.TimeoutException as err:
        raise NetworkError(f"Timeout contacting {endpoint}: {err}") from err
    except httpx.HTTPError as err:
        raise NetworkError(f"HTTP error contacting {endpoint}: {err}") from err

    if resp.status_code == 200:
        try:
            payload = resp.json()
        except ValueError as err:
            raise AuthError(f"Companion endpoint returned non-JSON: {err}") from err
        return _parse_companion_payload(payload)

    # 401/403 — bad SberID token (нужен refresh SberID)
    payload = _safe_json(resp)
    if resp.status_code in (401, 403):
        raise AuthError(
            f"Companion exchange rejected ({resp.status_code}): {payload or resp.text[:200]}"
        )
    raise ApiError(
        resp.status_code,
        message=str(payload or resp.text[:200] or "companion exchange failed"),
        payload=payload,
    )


def _parse_companion_payload(payload: dict) -> CompanionTokens:
    """Распарсить ответ companion endpoint.

    Поддерживается два формата:
    - **Modern** (OAuth2-style): `{"access_token": "...", "expires_in": ..., ...}`
    - **Legacy**: `{"token": "..."}` — старый формат, использовался до 2026.
      `expires_in` неизвестен → дефолт 24h.
    """
    if "access_token" in payload:
        return CompanionTokens.from_dict(payload)
    if "token" in payload:
        return CompanionTokens(access_token=payload["token"])
    raise AuthError(f"Companion response missing access_token/token: {payload}")


def _safe_json(resp: httpx.Response) -> dict | None:
    try:
        data = resp.json()
        return data if isinstance(data, dict) else None
    except ValueError:
        return None
