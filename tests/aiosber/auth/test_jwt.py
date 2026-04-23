"""Tests for `decode_jwt_unverified` — minimal JWT decoder для OIDC sub."""

from __future__ import annotations

import base64
import json

import pytest

from custom_components.sberhome.aiosber.auth import decode_jwt_unverified
from custom_components.sberhome.aiosber.exceptions import PkceError


def _make_jwt(payload: dict) -> str:
    """Собрать JWT-подобную строку с произвольным payload.

    Header и signature — dummies, т.к. `decode_jwt_unverified` не валидирует.
    """

    def b64(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = b64({"alg": "RS256", "typ": "JWT"})
    payload_b64 = b64(payload)
    signature = "fake-signature"
    return f"{header}.{payload_b64}.{signature}"


def test_decode_jwt_returns_payload() -> None:
    """Happy path: JWT с sub clean'м декодируется корректно."""
    jwt = _make_jwt({"sub": "user-12345", "aud": "client-app", "iat": 1700000000})
    result = decode_jwt_unverified(jwt)
    assert result["sub"] == "user-12345"
    assert result["aud"] == "client-app"


def test_decode_jwt_handles_missing_padding() -> None:
    """base64url без padding (стандарт JWT) должен декодироваться.

    Длина payload влияет на нужду в padding (1, 2 или 0 знаков `=`).
    Проверяем что все варианты работают.
    """
    for i in range(1, 15):
        payload = {"sub": "a" * i}
        jwt = _make_jwt(payload)
        assert decode_jwt_unverified(jwt)["sub"] == "a" * i


def test_decode_jwt_raises_on_wrong_parts_count() -> None:
    """Если токен не имеет 3 частей через точку — ошибка."""
    with pytest.raises(PkceError, match="expected 3 parts"):
        decode_jwt_unverified("single-part")
    with pytest.raises(PkceError, match="expected 3 parts"):
        decode_jwt_unverified("two.parts")


def test_decode_jwt_raises_on_invalid_base64() -> None:
    """Payload с не-base64 символами → PkceError."""
    with pytest.raises(PkceError):
        decode_jwt_unverified("header.not base64!@#.signature")


def test_decode_jwt_raises_on_invalid_json() -> None:
    """Payload — валидный base64, но не JSON (например, plain text) → PkceError."""
    garbage = base64.urlsafe_b64encode(b"not json").rstrip(b"=").decode()
    jwt = f"header.{garbage}.signature"
    with pytest.raises(PkceError, match="JSON"):
        decode_jwt_unverified(jwt)


def test_decode_jwt_raises_on_non_object_payload() -> None:
    """Payload валидный JSON, но не объект (массив/число) → PkceError."""
    arr = base64.urlsafe_b64encode(b"[1, 2, 3]").rstrip(b"=").decode()
    jwt = f"header.{arr}.signature"
    with pytest.raises(PkceError, match="must be a JSON object"):
        decode_jwt_unverified(jwt)
