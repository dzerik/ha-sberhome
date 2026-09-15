"""Тесты SberIdBearerAuth — сырой SberID access_token с auto-refresh."""

from __future__ import annotations

import asyncio
import time
from urllib.parse import parse_qs

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import SberIdBearerAuth, SberIdTokens
from custom_components.sberhome.aiosber.exceptions import InvalidGrant, NetworkError

_TOKEN_PATH = "/CSAFront/api/service/oidc/v3/token"


def _expired(*, refresh_token: str | None = "RT1") -> SberIdTokens:
    return SberIdTokens(
        access_token="SID_OLD",
        refresh_token=refresh_token,
        id_token="eyJhbGciOiJSUzI1NiJ9.old.sig",
        expires_in=3600,
        scope="openid",
        obtained_at=time.time() - 7200,
    )


def _fresh() -> SberIdTokens:
    return SberIdTokens(access_token="SID_OLD", refresh_token="RT1", expires_in=3600)


def _token_response(**overrides) -> httpx.Response:
    payload = {
        "access_token": "SID_NEW",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "RT2",
        "scope": "openid",
        "id_token": "eyJhbGciOiJSUzI1NiJ9.new.sig",
    }
    payload.update(overrides)
    return httpx.Response(200, json={k: v for k, v in payload.items() if v is not None})


class _TokenEndpoint:
    """MockTransport-обработчик token endpoint: считает обмены и отдаёт ответы."""

    def __init__(self, *responses: httpx.Response | Exception) -> None:
        self._responses = list(responses)
        self.forms: list[dict[str, list[str]]] = []

    async def __call__(self, req: httpx.Request) -> httpx.Response:
        assert req.url.path == _TOKEN_PATH, req.url
        self.forms.append(parse_qs(req.content.decode()))
        # Даём соседним задачам встать в очередь на lock во время обмена.
        await asyncio.sleep(0)
        item = self._responses[min(len(self.forms), len(self._responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item


async def test_fresh_token_returned_without_http():
    endpoint = _TokenEndpoint()
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _fresh())
        assert await auth.access_token() == "SID_OLD"
    assert endpoint.forms == []


async def test_expired_token_is_refreshed_and_persisted():
    endpoint = _TokenEndpoint(_token_response())
    persisted: list[SberIdTokens] = []

    async def on_refreshed(tokens: SberIdTokens) -> None:
        persisted.append(tokens)

    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _expired(), on_refreshed=on_refreshed, client_id="cid-1")
        assert await auth.access_token() == "SID_NEW"
        # Второй вызов — токен уже свежий, обмена нет.
        assert await auth.access_token() == "SID_NEW"

    assert len(endpoint.forms) == 1
    form = endpoint.forms[0]
    assert form["grant_type"] == ["refresh_token"]
    assert form["refresh_token"] == ["RT1"]
    assert form["client_id"] == ["cid-1"]
    assert [t.refresh_token for t in persisted] == ["RT2"]


async def test_refresh_keeps_previous_refresh_token_when_not_rotated():
    """Backend не прислал refresh_token → прежний сохраняется для следующего обмена."""
    endpoint = _TokenEndpoint(_token_response(refresh_token=None))
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _expired())
        assert await auth.access_token() == "SID_NEW"
        # Принудительный повторный refresh снова идёт с RT1.
        await auth.force_refresh()

    assert [f["refresh_token"] for f in endpoint.forms] == [["RT1"], ["RT1"]]


async def test_concurrent_expired_access_performs_single_refresh():
    endpoint = _TokenEndpoint(_token_response())
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _expired())
        tokens = await asyncio.gather(*(auth.access_token() for _ in range(5)))

    assert tokens == ["SID_NEW"] * 5
    assert len(endpoint.forms) == 1


async def test_force_refresh_skips_when_stale_token_already_replaced():
    endpoint = _TokenEndpoint(_token_response())
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _fresh())
        await auth.force_refresh("SID_OLD")
        # Запрос с тем же устаревшим токеном пришёл позже — обмен уже был.
        await auth.force_refresh("SID_OLD")
        assert await auth.access_token() == "SID_NEW"

    assert len(endpoint.forms) == 1


async def test_missing_refresh_token_raises_invalid_grant_without_http():
    endpoint = _TokenEndpoint()
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _expired(refresh_token=None))
        with pytest.raises(InvalidGrant, match="refresh_token missing"):
            await auth.access_token()
    assert endpoint.forms == []


async def test_revoked_refresh_token_is_not_retried():
    """invalid_grant окончателен: последующие запросы не бьют в Sber повторно."""
    endpoint = _TokenEndpoint(
        httpx.Response(400, json={"error": "invalid_grant", "error_description": "revoked"})
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _expired())
        with pytest.raises(InvalidGrant):
            await auth.access_token()
        with pytest.raises(InvalidGrant):
            await auth.force_refresh()

    assert len(endpoint.forms) == 1


async def test_transient_failure_shared_with_waiters_then_retried():
    """Сетевой сбой получают все ждавшие lock, но следующий вызов пробует снова."""
    endpoint = _TokenEndpoint(httpx.ConnectError("connection refused"), _token_response())
    async with httpx.AsyncClient(transport=httpx.MockTransport(endpoint)) as http:
        auth = SberIdBearerAuth(http, _expired())
        results = await asyncio.gather(
            *(auth.access_token() for _ in range(3)), return_exceptions=True
        )
        assert all(isinstance(r, NetworkError) for r in results), results
        assert len(endpoint.forms) == 1

        assert await auth.access_token() == "SID_NEW"

    assert len(endpoint.forms) == 2
