"""CSAFront SMS/email-OTP auth flow (beta path).

**Механизм и алгоритм полностью взят из открытого проекта
[shuryak/sberdevices](https://github.com/shuryak/sberdevices) (Go, MIT)**.
Endpoint'ы, body-shape, anti-bot `rsa_data`, persistent `X-Device-ID`,
refresh-rotation — переиспользованы оттуда без изменений по существу;
здесь они портированы на Python/asyncio и интегрированы в общий
`aiosber`-стек (auth manager, token store, transport).

Альтернативный путь авторизации, минующий Sber ID OAuth (`id.sber.ru`):

1. `send_otp(http, phone, pkce)` — заявка на SMS-OTP, возвращает `ouid`.
2. `verify_otp(http, ouid, otp)` — authcode или EmailOtpChallenge;
   дополнительный email-фактор инициализируется через `initialize_email_otp`.
3. `exchange_authcode(http, authcode, pkce)` — `authcode` → CSAFront
   access + refresh токены.
4. `get_smart_home_token(http, csafront_access)` — CSAFront access →
   SmartHomeToken (используется как X-AUTH-jwt для gateway).
5. `refresh_csafront(http, refresh_token)` — обновить CSAFront пару
   через `grant_type=refresh_token`. **Refresh rotation**: возвращаемый
   refresh_token заменяет старый, ОБЯЗАТЕЛЬНО persist'им.
"""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

import httpx

from ..const import (
    CSAFRONT_AUTHENTICATE_URL,
    CSAFRONT_CLIENT_ID,
    CSAFRONT_INITIALIZE_URL,
    CSAFRONT_REDIRECT_URI,
    CSAFRONT_SMARTHOME_TOKEN_URL,
    CSAFRONT_VERIFY_URL,
    TOKEN_ENDPOINT,
)
from ..exceptions import ApiError, AuthError, InvalidGrant, NetworkError
from .pkce import PkceParams

_LOGGER = logging.getLogger(__name__)

# Anti-bot ритуал (статические литералы, как в open-source reference flow).
# Sber backend проверяет наличие этих полей в `rsa_data`, но не валидирует
# их содержимое для server-side flow.
_RSA_DATA = {
    "deviceprint": "{}",
    "htmlinjection": "htmlinjection",
    "dom_elements": "dom_elements",
    "manvsmachinedetection": "manvsmachinedetection",
    "js_events": "js_events",
}

# Realistic browser User-Agent — gateway отдаёт HTML challenge для
# неизвестных клиентов.
_CSAFRONT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    "Origin": "https://online.sberbank.ru",
}


@dataclass(frozen=True, slots=True)
class EmailOtpChallenge:
    """Email confirmation required within the current CSAFront operation."""

    ouid: str = field(repr=False)
    initialization_required: bool = True


class UnsupportedAuthenticator(AuthError):
    """The server requires a factor this client cannot complete."""


class AuthSessionExpired(AuthError):
    """The authorization operation no longer exists or has timed out."""


async def _post_otp(
    http: httpx.AsyncClient,
    url: str,
    body: dict[str, Any],
    stage: str,
    *,
    checking_code: bool = False,
) -> dict[str, Any]:
    """Send an OTP operation without exposing provider payloads in exceptions."""
    headers = {**_CSAFRONT_HEADERS, "Referer": "SD", "Content-Type": "application/json"}
    try:
        resp = await http.post(url, json=body, headers=headers)
    except httpx.TimeoutException as err:
        raise NetworkError(f"{stage} timeout") from err
    except httpx.HTTPError as err:
        raise NetworkError(f"{stage} transport error") from err
    if resp.status_code != 200:
        try:
            error = resp.json().get("error")
        except (ValueError, AttributeError):
            error = None
        code = error.get("code") if isinstance(error, dict) else None
        if code in ("no_operation", "operation_timeout"):
            raise AuthSessionExpired(f"{stage}: authorization session expired")
        if checking_code and resp.status_code in (400, 401, 403):
            raise InvalidGrant(f"{stage} rejected: {resp.status_code}")
        raise AuthError(f"{stage} failed: {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as err:
        raise AuthError(f"{stage}: invalid JSON") from err
    if not isinstance(data, dict):
        raise AuthError(f"{stage}: expected JSON object")
    return data


def _rand_str(n: int) -> str:
    """Случайная строка длины n для nonce/state."""
    return secrets.token_urlsafe(n)[:n]


async def send_otp(http: httpx.AsyncClient, phone: str, pkce: PkceParams) -> str:
    """Шаг 1: запросить SMS-OTP на номер. Возвращает `ouid` для verify.

    Args:
        http: pre-built httpx.AsyncClient (с правильным SSL).
        phone: номер в формате E.164 без `+` (например `78001002030`).
        pkce: PKCE-пара (verifier + challenge) — `challenge` улетает на
            сервер, `verifier` потом нужен в `exchange_authcode`.

    Raises:
        AuthError: backend отверг запрос (некорректный phone и т.п.).
        NetworkError: проблемы с сетью.
    """
    body = {
        "authenticator": {"type": "sms_otp"},
        "identifier": {"type": "phone", "data": {"value": phone}},
        "channel": {
            "type": "web",
            "data": {
                "rsa_data": _RSA_DATA,
                "oidc": {
                    "code_challenge_method": "S256",
                    "nonce": _rand_str(64),
                    "scope": "openid",
                    "redirect_uri": CSAFRONT_REDIRECT_URI,
                    "code_challenge": pkce.challenge,
                    "state": _rand_str(64),
                    "client_id": CSAFRONT_CLIENT_ID,
                    "response_type": "code",
                },
            },
        },
    }
    data = await _post_otp(http, CSAFRONT_AUTHENTICATE_URL, body, "send_otp")
    ouid = data.get("ouid")
    if not ouid:
        raise AuthError("send_otp: no 'ouid' in response")
    return str(ouid)


async def verify_otp(
    http: httpx.AsyncClient,
    ouid: str,
    otp: str,
    *,
    authenticator: Literal["sms_otp", "email_otp"] = "sms_otp",
) -> str | EmailOtpChallenge:
    """Проверить OTP: вернуть authcode или требование email-подтверждения.

    Args:
        ouid: returned by `send_otp`.
        otp: Код из SMS или email.
        authenticator: Фактор, которому соответствует код.

    Raises:
        InvalidGrant: OTP неверный или просрочен. Пользователю показать
            "введите правильный код".
        AuthError: другие auth-ошибки.
        NetworkError: проблемы с сетью.
    """
    body = {
        "authenticator": {"type": authenticator, "data": {"value": otp}},
        "identifier": {"type": "ouid", "data": {"value": ouid}},
        "channel": {"type": "web", "data": {"rsa_data": _RSA_DATA}},
    }
    data = await _post_otp(http, CSAFRONT_VERIFY_URL, body, "verify_otp", checking_code=True)
    authcode = _extract_authcode(data)
    if authcode:
        return authcode
    factors = data.get("authenticator")
    if factors:
        if (
            isinstance(factors, list)
            and len(factors) == 1
            and isinstance(factors[0], dict)
            and factors[0].get("type") == "email_otp"
        ):
            return EmailOtpChallenge(
                ouid=ouid,
                initialization_required=factors[0].get("initialization_required") is not False,
            )
        raise UnsupportedAuthenticator("verify_otp: unsupported confirmation factor")
    raise AuthError("verify_otp: no authcode in response")


async def initialize_email_otp(http: httpx.AsyncClient, ouid: str) -> str:
    """Request an email code and return the possibly rotated operation ID.

    Wire contract: official Sber ID r-97.0.0 initialize request builder.
    See openspec/changes/add-csafront-email-otp/protocol.md for provenance.
    """
    body = {
        "identifier": {"type": "ouid", "data": {"value": ouid}},
        "authenticator": {"type": "email_otp"},
        "channel": {"type": "web", "data": {"rsa_data": _RSA_DATA}},
    }
    data = await _post_otp(http, CSAFRONT_INITIALIZE_URL, body, "initialize_email_otp")
    factor = data.get("authenticator")
    if not isinstance(factor, dict) or factor.get("type") != "email_otp":
        raise UnsupportedAuthenticator("initialize_email_otp: unsupported confirmation factor")
    new_ouid = data.get("ouid", ouid)
    if not isinstance(new_ouid, str) or not new_ouid:
        raise AuthError("initialize_email_otp: invalid operation ID")
    return new_ouid


def _extract_authcode(data: Any) -> str | None:
    """Достать authcode из ответа /verify.

    Sber возвращает один из трёх вариантов:
    1. `{"response_data": {"authcode": "..."}}`
    2. `{"authcode": "..."}`
    3. `{"response_data": {"redirect_uri": "homuzapp://host?code=...&state=..."}}`
    """
    if not isinstance(data, dict):
        return None
    if "response_data" in data and isinstance(data["response_data"], dict):
        rd = data["response_data"]
        ac = rd.get("authcode") or rd.get("code")
        if isinstance(ac, str):
            return ac
        ru = rd.get("redirect_uri", "")
        if isinstance(ru, str) and "code=" in ru:
            qs = parse_qs(urlparse(ru).query)
            code_list = qs.get("code") or []
            if code_list:
                return code_list[0]
    ac = data.get("authcode") or data.get("code")
    return ac if isinstance(ac, str) else None


async def exchange_authcode(
    http: httpx.AsyncClient,
    authcode: str,
    pkce: PkceParams,
) -> dict[str, Any]:
    """Шаг 3: обмен authcode на CSAFront access + refresh.

    Args:
        authcode: returned by `verify_otp`.
        pkce: PKCE-пара (нужен `verifier`).

    Returns:
        Сырой dict ответа: `{access_token, refresh_token, expires_in, ...}`.
        Caller строит `CsafrontTokens` сам, потому что нужны ещё
        smart_home_token + client_uuid.

    Raises:
        AuthError, NetworkError, InvalidGrant.
    """
    body = {
        "grant_type": "authorization_code",
        "client_id": CSAFRONT_CLIENT_ID,
        "code": authcode,
        "redirect_uri": CSAFRONT_REDIRECT_URI,
        "code_verifier": pkce.verifier,
    }
    headers = {**_CSAFRONT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = await http.post(TOKEN_ENDPOINT, data=body, headers=headers)
    except httpx.TimeoutException as err:
        raise NetworkError("exchange_authcode timeout") from err
    except httpx.HTTPError as err:
        raise NetworkError("exchange_authcode transport error") from err

    if resp.status_code != 200:
        if resp.status_code in (400, 401):
            raise InvalidGrant(f"exchange_authcode rejected: {resp.status_code}")
        raise AuthError(f"exchange_authcode failed: {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as err:
        raise AuthError("exchange_authcode: invalid JSON") from err
    if "access_token" not in data:
        raise AuthError("exchange_authcode: no access_token")
    return data


async def get_smart_home_token(
    http: httpx.AsyncClient,
    csafront_access: str,
) -> str:
    """Шаг 4: CSAFront access → SmartHomeToken.

    SmartHomeToken используется как X-AUTH-jwt для Gateway API напрямую,
    без отдельного companion-обмена.

    Raises:
        AuthError если backend отказал.
        NetworkError при сетевых ошибках.
    """
    headers = {
        **_CSAFRONT_HEADERS,
        "Host": "mp-prom.salutehome.ru",
        "Authorization": f"Bearer {csafront_access}",
    }
    try:
        resp = await http.get(CSAFRONT_SMARTHOME_TOKEN_URL, headers=headers)
    except httpx.TimeoutException as err:
        raise NetworkError("get_smart_home_token timeout") from err
    except httpx.HTTPError as err:
        raise NetworkError("get_smart_home_token transport error") from err

    if resp.status_code != 200:
        if resp.status_code in (401, 403):
            raise InvalidGrant(f"smarthome/token rejected: {resp.status_code}")
        raise ApiError(
            resp.status_code,
            message="smarthome/token failed",
        )
    try:
        data = resp.json()
    except ValueError as err:
        raise AuthError("smarthome/token: invalid JSON") from err
    token = data.get("token")
    if not token:
        raise AuthError("smarthome/token: no 'token' in response")
    return str(token)


async def refresh_csafront(
    http: httpx.AsyncClient,
    refresh_token: str,
) -> dict[str, Any]:
    """Шаг 5: refresh CSAFront access_token через refresh_token.

    ВНИМАНИЕ — rotation: в ответе может прийти новый refresh_token,
    который заменяет старый. Caller обязан persist'нуть новый.

    Raises:
        InvalidGrant: refresh_token уже использован/отозван (нужен
            полный re-auth).
        AuthError: другие auth-ошибки.
        NetworkError: проблемы с сетью.
    """
    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    headers = {**_CSAFRONT_HEADERS, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        resp = await http.post(TOKEN_ENDPOINT, data=body, headers=headers)
    except httpx.TimeoutException as err:
        raise NetworkError("refresh_csafront timeout") from err
    except httpx.HTTPError as err:
        raise NetworkError("refresh_csafront transport error") from err

    if resp.status_code != 200:
        if resp.status_code in (400, 401):
            # 400 invalid_grant — refresh_token уже использован/протух.
            raise InvalidGrant(f"refresh_csafront rejected: {resp.status_code}")
        raise AuthError(f"refresh_csafront failed: {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as err:
        raise AuthError("refresh_csafront: invalid JSON") from err
    if "access_token" not in data:
        raise AuthError("refresh_csafront: no access_token")
    return data


__all__ = [
    "send_otp",
    "verify_otp",
    "exchange_authcode",
    "get_smart_home_token",
    "refresh_csafront",
]
