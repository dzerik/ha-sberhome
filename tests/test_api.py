"""Tests for api.py — SberAPI shim (PKCE OAuth для config_flow) + shared SSL.

Никаких реальных HTTP: token exchange мокается на уровне
`custom_components.sberhome.api.exchange_code_for_tokens`, SSL-context
собирается локально (in-memory cadata, без сети).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest

from custom_components.sberhome.aiosber.auth import SberIdTokens
from custom_components.sberhome.aiosber.exceptions import AuthError, NetworkError
from custom_components.sberhome.api import (
    _SSL_PROVIDER_KEY,
    SberAPI,
    _normalize_legacy_token,
    async_init_ssl,
)

from .conftest import MOCK_TOKEN


class TestNormalizeLegacyToken:
    def test_converts_expires_at_to_obtained_at(self):
        """Legacy authlib-токен (expires_at) → obtained_at = expires_at - expires_in."""
        legacy = {**MOCK_TOKEN, "expires_at": 1_700_000_000}
        normalized = _normalize_legacy_token(legacy)
        assert normalized["obtained_at"] == 1_700_000_000 - 3600

    def test_keeps_token_with_obtained_at_untouched(self):
        """aiosber-формат (уже с obtained_at) не модифицируется."""
        token = {**MOCK_TOKEN, "obtained_at": 123.0}
        assert _normalize_legacy_token(token) is token

    def test_keeps_token_without_expires_at_untouched(self):
        """Без expires_at конвертировать нечего — возвращается как есть."""
        assert _normalize_legacy_token(MOCK_TOKEN) is MOCK_TOKEN


class TestSberApiTokens:
    def test_token_none_for_fresh_flow(self):
        """Без сохранённого токена property token/sberid_tokens — None."""
        api = SberAPI(http=MagicMock())
        assert api.token is None
        assert api.sberid_tokens is None

    def test_token_roundtrip_from_config_entry(self):
        """Сохранённый token dict восстанавливается в SberIdTokens и сериализуется обратно."""
        api = SberAPI(token={**MOCK_TOKEN, "obtained_at": 42.0}, http=MagicMock())
        assert api.sberid_tokens is not None
        assert api.sberid_tokens.access_token == "test_access_token"
        assert api.token["refresh_token"] == "test_refresh_token"
        assert api.token["obtained_at"] == 42.0

    def test_legacy_token_normalized_on_load(self):
        """Legacy-токен с expires_at принимается без ошибок (норм-ция на входе)."""
        api = SberAPI(token={**MOCK_TOKEN, "expires_at": 1_700_000_000}, http=MagicMock())
        assert api.sberid_tokens.obtained_at == 1_700_000_000 - 3600


class TestAuthorizationUrl:
    def test_url_contains_pkce_params(self):
        """create_authorization_url генерирует PKCE и кладёт challenge/state в query."""
        api = SberAPI(http=MagicMock())
        url = api.create_authorization_url()
        qs = parse_qs(urlparse(url).query)
        assert qs["response_type"] == ["code"]
        assert qs["code_challenge_method"] == ["S256"]
        assert qs["code_challenge"][0]
        assert qs["state"][0]
        assert "client_id" in qs


class TestAuthorizeByUrl:
    @pytest.mark.asyncio
    async def test_false_without_prior_authorization_url(self):
        """authorize_by_url без create_authorization_url → False (нет PKCE)."""
        api = SberAPI(http=MagicMock())
        assert await api.authorize_by_url("companionapp://host?code=ABC") is False

    @pytest.mark.asyncio
    async def test_false_on_state_mismatch(self):
        """CSRF-защита: state в callback не совпал → False, токен не сохранён."""
        api = SberAPI(http=MagicMock())
        api.create_authorization_url()
        ok = await api.authorize_by_url("companionapp://host?code=ABC&state=WRONG")
        assert ok is False
        assert api.token is None

    @pytest.mark.asyncio
    async def test_success_stores_tokens(self):
        """Успешный exchange → True, SberID-токены сохранены."""
        api = SberAPI(http=MagicMock())
        api.create_authorization_url()
        tokens = SberIdTokens(access_token="new_at", refresh_token="new_rt")
        with patch(
            "custom_components.sberhome.api.exchange_code_for_tokens",
            new=AsyncMock(return_value=tokens),
        ) as exchange:
            url = f"companionapp://host?code=ABC&state={api._pkce.state}"
            assert await api.authorize_by_url(url) is True
        # code из URL и verifier из PKCE ушли в exchange.
        assert exchange.await_args.args[1] == "ABC"
        assert exchange.await_args.kwargs["code_verifier"] == api._pkce.verifier
        assert api.token["access_token"] == "new_at"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("exc", [AuthError("denied"), NetworkError("timeout")])
    async def test_false_on_exchange_errors(self, exc):
        """Auth/network ошибки exchange глотаются → False (config_flow покажет ошибку)."""
        api = SberAPI(http=MagicMock())
        api.create_authorization_url()
        with patch(
            "custom_components.sberhome.api.exchange_code_for_tokens",
            new=AsyncMock(side_effect=exc),
        ):
            url = f"companionapp://host?code=ABC&state={api._pkce.state}"
            assert await api.authorize_by_url(url) is False
        assert api.token is None


class TestAclose:
    @pytest.mark.asyncio
    async def test_closes_own_client(self):
        """Клиент, созданный внутри (http=None), закрывается в aclose."""
        api = SberAPI()
        await api.aclose()
        assert api._http.is_closed

    @pytest.mark.asyncio
    async def test_injected_client_not_closed_by_default(self):
        """DI-клиент (owns_http по умолчанию False) остаётся открытым — им владеет caller."""
        http = MagicMock()
        http.aclose = AsyncMock()
        api = SberAPI(http=http)
        await api.aclose()
        http.aclose.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_injected_client_closed_when_owns_http(self):
        """config_flow-режим: owns_http=True → инжектированный клиент закрывается."""
        http = MagicMock()
        http.aclose = AsyncMock()
        api = SberAPI(http=http, owns_http=True)
        await api.aclose()
        http.aclose.assert_awaited_once()


class TestAsyncInitSsl:
    @pytest.mark.asyncio
    async def test_provider_cached_in_hass_data(self):
        """Первый вызов кладёт SslContextProvider в hass.data, второй — реюзает.

        SSL-context один и тот же объект (создаётся единожды на HA instance).
        """
        hass = MagicMock()
        hass.data = {}
        ctx1 = await async_init_ssl(hass)
        provider = hass.data[_SSL_PROVIDER_KEY]
        ctx2 = await async_init_ssl(hass)
        assert ctx1 is ctx2
        assert hass.data[_SSL_PROVIDER_KEY] is provider
