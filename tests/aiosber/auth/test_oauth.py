"""Тесты oauth.py — token exchange, refresh, error mapping."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import (
    exchange_code_for_tokens,
    refresh_sberid_tokens,
)
from custom_components.sberhome.aiosber.exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---- exchange_code_for_tokens ----
async def test_exchange_code_success():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["headers"] = dict(req.headers)
        captured["body"] = req.content.decode()
        return httpx.Response(
            200,
            json={
                "access_token": "AT",
                "refresh_token": "RT",
                "id_token": "JWT",
                "expires_in": 3600,
                "token_type": "Bearer",
            },
        )

    async with _client(handler) as http:
        tokens = await exchange_code_for_tokens(http, "code123", "verifier-xyz")

    assert tokens.access_token == "AT"
    assert tokens.refresh_token == "RT"
    # httpx normalizes header names to lowercase
    assert "rquid" in captured["headers"]
    assert "code=code123" in captured["body"]
    assert "code_verifier=verifier-xyz" in captured["body"]
    assert "grant_type=authorization_code" in captured["body"]


async def test_exchange_code_invalid_grant_raises_invalid_grant():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_grant", "error_description": "code expired"},
        )

    async with _client(handler) as http:
        with pytest.raises(InvalidGrant, match="code expired"):
            await exchange_code_for_tokens(http, "bad", "v")


async def test_exchange_code_other_400_raises_auth_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": "invalid_client", "error_description": "wrong client"},
        )

    async with _client(handler) as http:
        with pytest.raises(AuthError, match="invalid_client"):
            await exchange_code_for_tokens(http, "x", "v")


async def test_exchange_code_5xx_raises_api_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "service_down"})

    async with _client(handler) as http:
        with pytest.raises(ApiError) as exc_info:
            await exchange_code_for_tokens(http, "x", "v")
    assert exc_info.value.status_code == 503


async def test_exchange_code_network_error_mapped():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS down")

    async with _client(handler) as http:
        with pytest.raises(NetworkError, match="DNS down"):
            await exchange_code_for_tokens(http, "x", "v")


async def test_exchange_code_missing_access_token_raises_auth_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"refresh_token": "no AT here"})

    async with _client(handler) as http:
        with pytest.raises(AuthError, match="missing access_token"):
            await exchange_code_for_tokens(http, "x", "v")


async def test_exchange_code_non_json_raises_auth_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>nope</html>")

    async with _client(handler) as http:
        with pytest.raises(AuthError, match="non-JSON"):
            await exchange_code_for_tokens(http, "x", "v")


# ---- refresh_sberid_tokens ----
async def test_refresh_success():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["body"] = req.content.decode()
        return httpx.Response(
            200,
            json={"access_token": "NEW_AT", "refresh_token": "NEW_RT", "expires_in": 3600},
        )

    async with _client(handler) as http:
        new_tokens = await refresh_sberid_tokens(http, "OLD_RT")

    assert new_tokens.access_token == "NEW_AT"
    assert new_tokens.refresh_token == "NEW_RT"
    assert "grant_type=refresh_token" in captured["body"]
    assert "refresh_token=OLD_RT" in captured["body"]


async def test_refresh_invalid_grant():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with _client(handler) as http:
        with pytest.raises(InvalidGrant):
            await refresh_sberid_tokens(http, "expired-rt")
