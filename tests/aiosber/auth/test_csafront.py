"""Тесты CSAFront SMS-OTP wire-format flow."""

from __future__ import annotations

import json

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import PkceParams
from custom_components.sberhome.aiosber.auth.csafront import (
    AuthSessionExpired,
    EmailOtpChallenge,
    UnsupportedAuthenticator,
    _extract_authcode,
    exchange_authcode,
    get_smart_home_token,
    initialize_email_otp,
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


async def test_verify_sms_returns_email_challenge_instead_of_rejecting_login():
    """Issue #80: a valid SMS can require another factor rather than return authcode."""

    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "authenticator": [{"type": "email_otp", "initialization_required": True}],
                "response_data": {"toc": "redacted-toc"},
            },
        )

    async with _client(handler) as http:
        result = await verify_otp(http, "sms-session", "123456")

    assert result.ouid == "sms-session"
    assert result.initialization_required is True


@pytest.mark.parametrize("rotated", [True, False])
async def test_email_initialize_then_verify_uses_current_ouid_and_same_cookies(rotated):
    """Contract from the official client; responses are sanitized synthetic examples."""
    ouid = "email-operation" if rotated else "sms-session"
    requests = []

    async def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        body = json.loads(req.content)
        assert body["authenticator"]["type"] == "email_otp"
        assert body["channel"]["type"] == "web"
        assert "rsa_data" in body["channel"]["data"]
        assert req.headers["Referer"] == "SD"
        if req.url.path.endswith("/initialize"):
            assert body["identifier"]["data"]["value"] == "sms-session"
            assert "data" not in body["authenticator"]
            reply = {"authenticator": {"type": "email_otp", "lifetime": 180, "data": {}}}
            if rotated:
                reply["ouid"] = ouid
            return httpx.Response(200, json=reply, headers={"Set-Cookie": "session=fake; Path=/"})
        assert body["identifier"]["data"]["value"] == ouid
        assert body["authenticator"]["data"]["value"] == "654321"
        assert req.headers["Cookie"] == "session=fake"
        return httpx.Response(200, json={"response_data": {"authcode": "email-authcode"}})

    async with _client(handler) as http:
        current = await initialize_email_otp(http, "sms-session")
        result = await verify_otp(http, current, "654321", authenticator="email_otp")
    assert result == "email-authcode"
    assert [r.url.path for r in requests] == [
        "/CSAFront/uapi/v2/initialize",
        "/CSAFront/uapi/v2/verify",
    ]


@pytest.mark.parametrize("required", [True, False, None])
async def test_email_challenge_tracks_initialization(required):
    async def handler(req):
        factor = {"type": "email_otp"}
        if required is not None:
            factor["initialization_required"] = required
        return httpx.Response(200, json={"authenticator": [factor]})

    async with _client(handler) as http:
        result = await verify_otp(http, "private-operation", "123456")
    assert isinstance(result, EmailOtpChallenge)
    assert result.initialization_required is (required is not False)
    assert "private-operation" not in repr(result)


@pytest.mark.parametrize(
    "factors",
    [
        "email_otp",
        {"type": "email_otp"},
        [None],
        [{"type": "pat_push"}],
        [{"type": "email_otp"}, {"type": "pat_push"}],
    ],
)
async def test_verify_rejects_unsupported_or_ambiguous_factors(factors):
    async def handler(req):
        return httpx.Response(200, json={"authenticator": factors})

    async with _client(handler) as http:
        with pytest.raises(UnsupportedAuthenticator):
            await verify_otp(http, "operation", "123456")


@pytest.mark.parametrize("factor", [None, [], {"type": "pat_push"}])
async def test_initialize_rejects_unsupported_factor(factor):
    async def handler(req):
        return httpx.Response(200, json={"authenticator": factor})

    async with _client(handler) as http:
        with pytest.raises(UnsupportedAuthenticator):
            await initialize_email_otp(http, "operation")


@pytest.mark.parametrize("ouid", [None, "", 123])
async def test_initialize_rejects_invalid_new_operation_id(ouid):
    async def handler(req):
        return httpx.Response(200, json={"ouid": ouid, "authenticator": {"type": "email_otp"}})

    async with _client(handler) as http:
        with pytest.raises(AuthError, match="operation ID"):
            await initialize_email_otp(http, "operation")


@pytest.mark.parametrize("stage", ["initialize", "verify"])
@pytest.mark.parametrize("code", ["no_operation", "operation_timeout"])
async def test_expired_otp_operation_is_distinguished_from_wrong_code(stage, code):
    async def handler(req):
        return httpx.Response(403, json={"error": {"code": code}})

    async with _client(handler) as http:
        with pytest.raises(AuthSessionExpired):
            if stage == "initialize":
                await initialize_email_otp(http, "operation")
            else:
                await verify_otp(http, "operation", "123456", authenticator="email_otp")


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


# ----- ошибки транспорта и ответа для всех шагов ---------------------------

_PKCE = PkceParams.generate()

_STEPS = {
    "initialize_email_otp": lambda http: initialize_email_otp(http, "ouid-1"),
    "send_otp": lambda http: send_otp(http, "78001002030", _PKCE),
    "verify_otp": lambda http: verify_otp(http, "ouid-1", "123456"),
    "exchange_authcode": lambda http: exchange_authcode(http, "ac-1", _PKCE),
    "get_smart_home_token": lambda http: get_smart_home_token(http, "ax"),
    "refresh_csafront": lambda http: refresh_csafront(http, "rx"),
}


@pytest.mark.parametrize("step", sorted(_STEPS))
@pytest.mark.parametrize("status", [200, 400, 503])
async def test_auth_failures_do_not_expose_provider_payloads(step, status):
    private = "fake-otp-authcode-toc-refresh-secret"

    async def handler(req):
        return httpx.Response(status, json={"debug": private, "response_data": {"toc": private}})

    async with _client(handler) as http:
        with pytest.raises((AuthError, ApiError)) as exc:
            await _STEPS[step](http)
    assert private not in str(exc.value)


@pytest.mark.parametrize("payload", [[], "not-object", None])
async def test_otp_request_rejects_non_object_response(payload):
    async def handler(req):
        return httpx.Response(200, json=payload)

    async with _client(handler) as http:
        with pytest.raises(AuthError, match="JSON object|invalid JSON"):
            await initialize_email_otp(http, "operation")


def _raising(exc: Exception):
    async def handler(req: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize("step", sorted(_STEPS))
@pytest.mark.parametrize(
    "exc",
    [httpx.ReadTimeout("read timed out"), httpx.RemoteProtocolError("peer closed")],
    ids=["timeout", "transport"],
)
async def test_step_wraps_transport_failures_as_network_error(step, exc):
    """Таймаут и обрыв соединения на любом шаге → NetworkError, не сырой httpx."""
    http = _client(_raising(exc))
    with pytest.raises(NetworkError, match=step):
        await _STEPS[step](http)
    await http.aclose()


@pytest.mark.parametrize("step", sorted(_STEPS))
async def test_step_rejects_html_challenge_instead_of_json(step):
    """Anti-bot шлюз отвечает HTML-страницей со статусом 200 → AuthError."""

    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>Checking your browser…</body></html>")

    http = _client(handler)
    with pytest.raises(AuthError, match="invalid JSON"):
        await _STEPS[step](http)
    await http.aclose()


@pytest.mark.parametrize(
    ("step", "match"),
    [
        ("verify_otp", "no authcode"),
        ("exchange_authcode", "no access_token"),
        ("get_smart_home_token", "no 'token'"),
        ("refresh_csafront", "no access_token"),
    ],
)
async def test_step_rejects_json_without_required_field(step, match):
    """200 с JSON, но без ключевого поля (например, `{"error": ...}`) → AuthError."""

    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"state": {"status": "PENDING"}})

    http = _client(handler)
    with pytest.raises(AuthError, match=match):
        await _STEPS[step](http)
    await http.aclose()


@pytest.mark.parametrize("step", ["verify_otp", "exchange_authcode", "refresh_csafront"])
async def test_step_server_error_is_auth_error_not_invalid_grant(step):
    """5xx — временная беда сервера: AuthError, но не InvalidGrant (без reauth)."""

    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Temporarily Unavailable")

    http = _client(handler)
    with pytest.raises(AuthError, match="503") as exc_info:
        await _STEPS[step](http)
    assert not isinstance(exc_info.value, InvalidGrant)
    await http.aclose()


async def test_verify_otp_reads_code_key_inside_response_data():
    async def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response_data": {"code": "ac-code"}})

    http = _client(handler)
    assert await verify_otp(http, "ouid", "123456") == "ac-code"
    await http.aclose()
