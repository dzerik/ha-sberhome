"""Тесты CSAFront SMS-OTP wire-format flow."""

from __future__ import annotations

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import PkceParams
from custom_components.sberhome.aiosber.auth.csafront import (
    _extract_authcode,
    exchange_authcode,
    get_smart_home_token,
    refresh_csafront,
    send_otp,
    verify_otp,
)
from custom_components.sberhome.aiosber.exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ----- send_otp ------------------------------------------------------------


async def test_send_otp_returns_ouid_on_200():
    async def handler(req: httpx.Request) -> httpx.Response:
        # Проверяем что в теле есть phone и pkce challenge.
        body = req.read()
        assert b"78001002030" in body
        return httpx.Response(200, json={"ouid": "ouid-XYZ", "authenticator": [{}]})

    http = _client(handler)
    pkce = PkceParams.generate()
    ouid = await send_otp(http, "78001002030", pkce)
    assert ouid == "ouid-XYZ"
    await http.aclose()


async def test_send_otp_raises_auth_error_on_400():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad phone")

    http = _client(handler)
    with pytest.raises(AuthError):
        await send_otp(http, "x", PkceParams.generate())
    await http.aclose()


async def test_send_otp_raises_auth_error_when_no_ouid():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"foo": "bar"})

    http = _client(handler)
    with pytest.raises(AuthError, match="no 'ouid'"):
        await send_otp(http, "78001002030", PkceParams.generate())
    await http.aclose()


async def test_send_otp_wraps_network_errors():
    async def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    http = _client(handler)
    with pytest.raises(NetworkError):
        await send_otp(http, "78001002030", PkceParams.generate())
    await http.aclose()


# ----- verify_otp ----------------------------------------------------------


async def test_verify_otp_extracts_authcode_flat_shape():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"authcode": "ac-123"})

    http = _client(handler)
    ac = await verify_otp(http, "ouid", "1234")
    assert ac == "ac-123"
    await http.aclose()


async def test_verify_otp_extracts_authcode_response_data_shape():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response_data": {"authcode": "ac-456"}})

    http = _client(handler)
    ac = await verify_otp(http, "ouid", "1234")
    assert ac == "ac-456"
    await http.aclose()


async def test_verify_otp_extracts_authcode_from_redirect_uri():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "response_data": {
                    "redirect_uri": "homuzapp://host?code=ac-789&state=xyz",
                }
            },
        )

    http = _client(handler)
    ac = await verify_otp(http, "ouid", "1234")
    assert ac == "ac-789"
    await http.aclose()


async def test_verify_otp_raises_invalid_grant_on_400():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="wrong otp")

    http = _client(handler)
    with pytest.raises(InvalidGrant):
        await verify_otp(http, "ouid", "wrong")
    await http.aclose()


def test_extract_authcode_helper_returns_none_for_garbage():
    # Не dict
    assert _extract_authcode("not-a-dict") is None  # type: ignore[arg-type]
    # Dict без authcode
    assert _extract_authcode({"foo": 1}) is None
    # response_data без useful поля
    assert _extract_authcode({"response_data": {"foo": 1}}) is None


# ----- exchange_authcode ---------------------------------------------------


async def test_exchange_authcode_returns_token_data():
    async def handler(req: httpx.Request) -> httpx.Response:
        body = req.read().decode()
        assert "grant_type=authorization_code" in body
        return httpx.Response(
            200,
            json={
                "access_token": "ax",
                "refresh_token": "rx",
                "expires_in": 1800,
            },
        )

    http = _client(handler)
    data = await exchange_authcode(http, "ac", PkceParams.generate())
    assert data["access_token"] == "ax"
    assert data["refresh_token"] == "rx"
    await http.aclose()


async def test_exchange_authcode_raises_invalid_grant_on_400():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="invalid_grant")

    http = _client(handler)
    with pytest.raises(InvalidGrant):
        await exchange_authcode(http, "ac", PkceParams.generate())
    await http.aclose()


# ----- get_smart_home_token ------------------------------------------------


async def test_get_smart_home_token_returns_token():
    async def handler(req: httpx.Request) -> httpx.Response:
        assert req.headers["Authorization"] == "Bearer ax"
        return httpx.Response(200, json={"token": "sht-XYZ", "state": {"status": "OK"}})

    http = _client(handler)
    sht = await get_smart_home_token(http, "ax")
    assert sht == "sht-XYZ"
    await http.aclose()


async def test_get_smart_home_token_raises_invalid_grant_on_401():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="expired")

    http = _client(handler)
    with pytest.raises(InvalidGrant):
        await get_smart_home_token(http, "expired")
    await http.aclose()


async def test_get_smart_home_token_raises_api_error_on_5xx():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="server down")

    http = _client(handler)
    with pytest.raises(ApiError):
        await get_smart_home_token(http, "ax")
    await http.aclose()


# ----- refresh_csafront ----------------------------------------------------


async def test_refresh_csafront_returns_rotated_tokens():
    async def handler(req: httpx.Request) -> httpx.Response:
        body = req.read().decode()
        assert "grant_type=refresh_token" in body
        return httpx.Response(
            200,
            json={
                "access_token": "new-ax",
                "refresh_token": "new-rx",
                "expires_in": 1800,
            },
        )

    http = _client(handler)
    new = await refresh_csafront(http, "old-rx")
    assert new["access_token"] == "new-ax"
    assert new["refresh_token"] == "new-rx"
    await http.aclose()


async def test_refresh_csafront_raises_invalid_grant_on_400():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='{"error":"invalid_grant"}')

    http = _client(handler)
    with pytest.raises(InvalidGrant):
        await refresh_csafront(http, "revoked")
    await http.aclose()
