"""Minimal JWT-декодер для OIDC id_token.

Нужен только для чтения `sub` claim'а (unique identifier пользователя в
Sber ID) — подпись НЕ верифицируется. Это стандартная OIDC-практика для
клиента, который получил токен по TLS напрямую от issuer: подпись
защищает от tampering в полёте, что TLS уже обеспечивает.

Pure function без сторонних зависимостей (PyJWT/python-jose не нужны —
CLAUDE.md запрещает добавлять deps в aiosber без reason).
"""

from __future__ import annotations

import base64
import json
from typing import Any

from ..exceptions import PkceError


def decode_jwt_unverified(token: str) -> dict[str, Any]:
    """Декодировать JWT payload БЕЗ верификации подписи.

    Args:
        token: JWT строка `header.payload.signature` (RFC 7519).

    Returns:
        Payload как dict (parsed JSON).

    Raises:
        PkceError: если токен не JWT (нет 3 частей) или payload не JSON.
    """
    try:
        _, payload_b64, _ = token.split(".")
    except ValueError as err:
        raise PkceError(f"Invalid JWT (expected 3 parts): {err}") from err

    # base64url без padding — дополняем до кратности 4
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded)
    except (ValueError, TypeError) as err:
        raise PkceError(f"Invalid JWT base64: {err}") from err

    try:
        payload = json.loads(raw)
    except ValueError as err:
        raise PkceError(f"Invalid JWT payload JSON: {err}") from err

    if not isinstance(payload, dict):
        raise PkceError(f"JWT payload must be a JSON object, got {type(payload).__name__}")

    return payload
