"""Тесты companion.exchange_for_companion_token."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import exchange_for_companion_token
from custom_components.sberhome.aiosber.exceptions import ApiError, AuthError, NetworkError


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_companion_success():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(req.headers)
        return httpx.Response(
            200,
            json={"access_token": "COMP", "refresh_token": "CR", "expires_in": 86400},
        )

    async with _client(handler) as http:
        tokens = await exchange_for_companion_token(http, "sberid-AT")

    assert tokens.access_token == "COMP"
    assert tokens.expires_in == 86400
    assert captured["headers"]["authorization"] == "Bearer sberid-AT"
    # Обязателен Salute User-Agent (бекенд Sber иначе возвращает 400)
    assert "user-agent" in captured["headers"]
    assert "Salute" in captured["headers"]["user-agent"]


async def test_companion_401_raises_auth_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_token"})

    async with _client(handler) as http:
        with pytest.raises(AuthError, match="rejected"):
            await exchange_for_companion_token(http, "bad-AT")


async def test_companion_5xx_raises_api_error():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="oops")

    async with _client(handler) as http:
        with pytest.raises(ApiError) as exc:
            await exchange_for_companion_token(http, "x")
    assert exc.value.status_code == 500


async def test_companion_network_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("slow")

    async with _client(handler) as http:
        with pytest.raises(NetworkError, match="Timeout"):
            await exchange_for_companion_token(http, "x")


async def test_companion_missing_access_token():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"refresh_token": "no AT"})

    async with _client(handler) as http:
        with pytest.raises(AuthError, match="missing access_token"):
            await exchange_for_companion_token(http, "x")


async def test_companion_legacy_format_token_field():
    """Legacy companion возвращает {"token": "..."} вместо {"access_token": "..."}."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token": "LEGACY_TOK"})

    async with _client(handler) as http:
        tokens = await exchange_for_companion_token(http, "AT")

    assert tokens.access_token == "LEGACY_TOK"
    assert tokens.expires_in == 86400  # default 24h


async def test_companion_custom_user_agent():
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["ua"] = req.headers.get("user-agent")
        return httpx.Response(200, json={"access_token": "x"})

    async with _client(handler) as http:
        await exchange_for_companion_token(http, "AT", user_agent="MyCustomUA/1.0")

    assert captured["ua"] == "MyCustomUA/1.0"
