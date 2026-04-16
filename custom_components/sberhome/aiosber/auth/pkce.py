"""OAuth2 PKCE — генерация verifier/challenge + URL builders.

Pure functions. Никаких HTTP-вызовов.

References:
- RFC 7636 (PKCE)
- research_docs/02-auth.md (полный flow для Sber)
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from typing import Self
from urllib.parse import parse_qs, urlencode, urlparse

from ..const import (
    AUTHORIZE_ENDPOINT,
    DEFAULT_CLIENT_ID,
    DEFAULT_REDIRECT_URI,
    DEFAULT_SCOPES,
)
from ..exceptions import PkceError

# RFC 7636: длина code_verifier — 43-128 символов
_VERIFIER_BYTES = 32  # → 43 base64url-символа без padding


@dataclass(slots=True, frozen=True)
class PkceParams:
    """Случайно сгенерированная пара verifier + challenge для одного OAuth-flow.

    Сохранять `verifier` ВСЁ время от authorize до token exchange.
    Безопасно сериализовать (например, в pending_auth_flows в HA).
    """

    verifier: str
    challenge: str
    state: str
    nonce: str

    method: str = "S256"

    @classmethod
    def generate(cls) -> Self:
        """Создать новый набор параметров с криптографически стойкой случайностью."""
        verifier = _generate_verifier()
        challenge = _challenge_from_verifier(verifier)
        state = secrets.token_urlsafe(16)
        nonce = secrets.token_urlsafe(16)
        return cls(verifier=verifier, challenge=challenge, state=state, nonce=nonce)


def _generate_verifier() -> str:
    """43-символьный base64url-encoded random."""
    return base64.urlsafe_b64encode(secrets.token_bytes(_VERIFIER_BYTES)).rstrip(b"=").decode()


def _challenge_from_verifier(verifier: str) -> str:
    """SHA256 → base64url без padding (RFC 7636 §4.2)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def build_authorize_url(
    pkce: PkceParams,
    *,
    client_id: str = DEFAULT_CLIENT_ID,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
    endpoint: str = AUTHORIZE_ENDPOINT,
) -> str:
    """Построить URL для редиректа пользователя на id.sber.ru.

    Пользователь:
    1. Открывает этот URL в браузере.
    2. Логинится через Sber ID.
    3. Браузер редиректит на `redirect_uri?code=...&state=...`.
    4. URL передаётся в `extract_code_from_redirect()` — получаем code.
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "state": pkce.state,
        "nonce": pkce.nonce,
        "scope": " ".join(scopes),
        "redirect_uri": redirect_uri,
        "code_challenge": pkce.challenge,
        "code_challenge_method": pkce.method,
    }
    return f"{endpoint}?{urlencode(params)}"


def extract_code_from_redirect(redirect_url: str, *, expected_state: str | None = None) -> str:
    """Извлечь authorization_code из callback URL.

    Args:
        redirect_url: Полный URL из адресной строки браузера после авторизации,
            типа `companionapp://host?code=ABC&state=XYZ`.
        expected_state: Если задан — проверяется на совпадение с `state` из URL.
            Бросает `PkceError` при несовпадении (защита от CSRF).

    Returns:
        authorization_code (строка).

    Raises:
        PkceError: если `code` отсутствует, или `state` не совпадает.
    """
    try:
        parsed = urlparse(redirect_url)
    except Exception as err:
        raise PkceError(f"Invalid redirect URL: {err}") from err

    qs = parse_qs(parsed.query)
    codes = qs.get("code")
    # Иногда параметры в fragment (после #), а не в query — пробуем оба места
    if not codes and parsed.fragment:
        qs = parse_qs(parsed.fragment)
        codes = qs.get("code")
    if not codes:
        raise PkceError(f"No 'code' in redirect URL: {redirect_url!r}")

    if expected_state is not None:
        states = qs.get("state", [])
        if not states or states[0] != expected_state:
            raise PkceError(
                f"State mismatch: expected {expected_state!r}, got {states[:1]!r}"
            )

    return codes[0]
