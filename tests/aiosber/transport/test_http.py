"""Тесты HttpTransport — auth, headers, retry, error mapping."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest

from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    CsafrontAuthManager,
    CsafrontTokens,
    InMemoryCsafrontTokenStore,
    InMemoryTokenStore,
    SberIdBearerAuth,
    SberIdTokens,
)
from custom_components.sberhome.aiosber.exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
    RateLimitError,
)
from custom_components.sberhome.aiosber.transport import HttpTransport


def _build(handler) -> tuple[HttpTransport, list[httpx.Request], InMemoryTokenStore]:
    """Helper: HttpTransport с MockTransport + готовым AuthManager."""
    hits: list[httpx.Request] = []

    def wrapper(req: httpx.Request) -> httpx.Response:
        hits.append(req)
        return handler(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(wrapper))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="TOK", expires_in=3600))
    auth = AuthManager(http=http, store=store)
    return HttpTransport(http=http, auth=auth), hits, store


# ---- Headers ----
async def test_request_signs_with_x_auth_jwt_header():
    """Gateway требует X-AUTH-jwt (без Bearer prefix), не стандартный Authorization."""

    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport, hits, _ = _build(h)
    async with transport:
        await transport.get("/devices/")

    assert hits[0].headers["x-auth-jwt"] == "TOK"
    # Authorization не должен ставиться — gateway его игнорирует
    assert "authorization" not in hits[0].headers


async def test_request_includes_user_agent_and_trace_id():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport, hits, _ = _build(h)
    async with transport:
        await transport.get("/devices/")

    assert "user-agent" in hits[0].headers
    assert "x-trace-id" in hits[0].headers


async def test_extra_headers_passed_through():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport, hits, _ = _build(h)
    async with transport:
        await transport.get("/devices/", headers={"X-Custom": "v"})

    assert hits[0].headers["x-custom"] == "v"


# ---- URL building ----
async def test_relative_path_prepended_with_base_url():
    def h(req: httpx.Request) -> httpx.Response:
        assert str(req.url).endswith("/gateway/v1/devices/")
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.get("devices/")


async def test_absolute_url_passed_as_is():
    def h(req: httpx.Request) -> httpx.Response:
        assert str(req.url) == "https://other.example.com/x"
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.get("https://other.example.com/x")


# ---- Verbs ----
async def test_post_with_json():
    captured: dict = {}

    def h(req: httpx.Request) -> httpx.Response:
        captured["method"] = req.method
        captured["body"] = req.content
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.post("/devices/", json={"x": 1})

    assert captured["method"] == "POST"
    assert b'"x": 1' in captured["body"] or b'"x":1' in captured["body"]


async def test_put_delete_patch_methods():
    methods_seen = []

    def h(req: httpx.Request) -> httpx.Response:
        methods_seen.append(req.method)
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    async with transport:
        await transport.put("/x")
        await transport.delete("/x")
        await transport.patch("/x")

    assert methods_seen == ["PUT", "DELETE", "PATCH"]


# ---- Retry on 401 ----
async def test_401_triggers_refresh_and_retry():
    """401 → force_refresh() → retry. Финальный 200 — успех."""
    state = {"first_call": True, "refreshed": False}

    def companion(req: httpx.Request) -> httpx.Response:
        state["refreshed"] = True
        return httpx.Response(200, json={"access_token": "NEW_TOK", "expires_in": 3600})

    def gateway(req: httpx.Request) -> httpx.Response:
        if state["first_call"]:
            state["first_call"] = False
            return httpx.Response(401, json={"error": "expired"})
        # После retry — токен должен быть новый
        assert req.headers["x-auth-jwt"] == "NEW_TOK"
        return httpx.Response(200, json={"ok": True})

    def router(req: httpx.Request) -> httpx.Response:
        if "smarthome/token" in req.url.path:
            return companion(req)
        return gateway(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        resp = await transport.get("/devices/")

    assert resp.status_code == 200
    assert state["refreshed"]


async def test_401_after_retry_raises_auth_error():
    """Если и после refresh токен снова 401 — AuthError."""

    def router(req: httpx.Request) -> httpx.Response:
        if "smarthome/token" in req.url.path:
            return httpx.Response(200, json={"access_token": "STILL_BAD", "expires_in": 3600})
        return httpx.Response(401, json={"error": "still bad"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        with pytest.raises(AuthError, match="Unauthorized after refresh"):
            await transport.get("/devices/")


# ---- Single-flight refresh on concurrent 401 ----
_PARALLEL = 4


class _CountingTokenStore(InMemoryTokenStore):
    """InMemoryTokenStore, считающий записи (аналог записи в config entry)."""

    def __init__(self, initial: CompanionTokens | None = None) -> None:
        super().__init__(initial)
        self.saves = 0

    async def save(self, tokens: CompanionTokens) -> None:
        self.saves += 1
        await super().save(tokens)


def _expired_sberid() -> SberIdTokens:
    return SberIdTokens(
        access_token="SID_OLD",
        refresh_token="RT1",
        expires_in=10,
        obtained_at=time.time() - 1000,
    )


class _Gateway:
    """Gateway, отвечающий 401 на старый токен только когда ВСЕ запросы его увидели.

    Барьер гарантирует, что N запросов действительно получили 401 с одним и
    тем же токеном до первого refresh, — иначе гонку не воспроизвести.
    """

    def __init__(self, *, header: str, bad: str, good: str) -> None:
        self.header = header
        self.bad = bad
        self.good = good
        self.hits: list[str] = []
        self._bad_seen = 0
        self._all_bad = asyncio.Event()

    async def __call__(self, req: httpx.Request) -> httpx.Response:
        token = req.headers.get(self.header, "")
        self.hits.append(token)
        if token.endswith(self.bad):
            self._bad_seen += 1
            if self._bad_seen >= _PARALLEL:
                self._all_bad.set()
            await self._all_bad.wait()
            return httpx.Response(401, json={"error": "expired"})
        assert token.endswith(self.good)
        return httpx.Response(200, json={"ok": True})


async def test_concurrent_401_share_one_refresh_and_one_persist():
    """N параллельных 401 → один refresh SberID, один обмен, одна запись токенов.

    Раньше каждый запрос под lock'ом заново делал обмен companion-токена и
    писал токены — шторм из N обменов и N записей config entry.
    """
    gateway = _Gateway(header="x-auth-jwt", bad="OLD", good="NEW")
    calls = {"sberid": 0, "companion": 0}

    async def router(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oidc/v3/token"):
            calls["sberid"] += 1
            # refresh_token одноразовый: повторное использование RT1 — отказ.
            if b"RT1" not in req.content:
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={"access_token": "SID_NEW", "refresh_token": "RT2", "expires_in": 3600},
            )
        if req.url.path.endswith("/smarthome/token"):
            calls["companion"] += 1
            return httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600})
        return await gateway(req)

    persisted: list[SberIdTokens] = []

    async def on_sberid_refreshed(tokens: SberIdTokens) -> None:
        persisted.append(tokens)

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = _CountingTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    auth = AuthManager(
        http=http,
        store=store,
        sberid_tokens=_expired_sberid(),
        on_sberid_refreshed=on_sberid_refreshed,
    )
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        responses = await asyncio.gather(*(transport.get("/devices/") for _ in range(_PARALLEL)))

    assert [r.status_code for r in responses] == [200] * _PARALLEL
    assert calls == {"sberid": 1, "companion": 1}
    assert store.saves == 1
    assert [t.refresh_token for t in persisted] == ["RT2"]
    # Каждый запрос: одна попытка со старым токеном + retry с новым.
    assert sorted(gateway.hits) == ["NEW"] * _PARALLEL + ["OLD"] * _PARALLEL


async def test_concurrent_401_refresh_failure_propagates_once():
    """Refresh упал (refresh_token отозван) → одна попытка, все запросы получают InvalidGrant.

    InvalidGrant — подкласс AuthError: coordinator переводит его в reauth,
    как и раньше. Ждавшие lock запросы не повторяют заведомо неудачный refresh.
    """
    gateway = _Gateway(header="x-auth-jwt", bad="OLD", good="NEW")
    calls = {"sberid": 0, "companion": 0}

    async def router(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oidc/v3/token"):
            calls["sberid"] += 1
            return httpx.Response(400, json={"error": "invalid_grant"})
        if req.url.path.endswith("/smarthome/token"):
            calls["companion"] += 1
            return httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600})
        return await gateway(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = _CountingTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    auth = AuthManager(http=http, store=store, sberid_tokens=_expired_sberid())
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        results = await asyncio.gather(
            *(transport.get("/devices/") for _ in range(_PARALLEL)), return_exceptions=True
        )

    assert all(isinstance(r, InvalidGrant) for r in results), results
    assert calls == {"sberid": 1, "companion": 0}
    assert store.saves == 0
    assert gateway.hits == ["OLD"] * _PARALLEL


async def test_concurrent_401_sberid_bearer_rotates_refresh_token_once():
    """Канал настроек (сырой SberID): N параллельных 401 → одна ротация и одна запись."""
    gateway = _Gateway(header="authorization", bad="SID_OLD", good="SID_NEW")
    calls = {"sberid": 0}

    async def router(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oidc/v3/token"):
            calls["sberid"] += 1
            return httpx.Response(
                200,
                json={"access_token": "SID_NEW", "refresh_token": "RT2", "expires_in": 3600},
            )
        return await gateway(req)

    persisted: list[SberIdTokens] = []

    async def on_refreshed(tokens: SberIdTokens) -> None:
        persisted.append(tokens)

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    auth = SberIdBearerAuth(
        http,
        SberIdTokens(access_token="SID_OLD", refresh_token="RT1", expires_in=3600),
        on_refreshed=on_refreshed,
    )
    transport = HttpTransport(
        http=http, auth=auth, auth_header_name="Authorization", auth_header_prefix="Bearer "
    )

    async with transport:
        responses = await asyncio.gather(*(transport.get("/x") for _ in range(_PARALLEL)))

    assert [r.status_code for r in responses] == [200] * _PARALLEL
    assert calls == {"sberid": 1}
    assert [t.refresh_token for t in persisted] == ["RT2"]


async def test_concurrent_401_csafront_rotates_refresh_token_once():
    """SMS-вход: N параллельных 401 → одна ротация CSAFront-пары и одна запись."""
    gateway = _Gateway(header="x-auth-jwt", bad="sht-old", good="sht-new")
    calls = {"refresh": 0, "smart": 0}

    async def router(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/oidc/v3/token"):
            calls["refresh"] += 1
            return httpx.Response(
                200,
                json={"access_token": "ax-new", "refresh_token": "rx-new", "expires_in": 1800},
            )
        if req.url.path.endswith("/smarthome/token"):
            calls["smart"] += 1
            return httpx.Response(200, json={"token": "sht-new"})
        return await gateway(req)

    now = time.time()
    initial = CsafrontTokens(
        csafront_access_token="ax-old",
        csafront_refresh_token="rx-old",
        smart_home_token="sht-old",
        client_uuid="cu-1",
        csafront_expires_in=1800,
        csafront_obtained_at=now,
        smart_home_obtained_at=now,
    )
    persisted: list[CsafrontTokens] = []

    async def on_refreshed(tokens: CsafrontTokens) -> None:
        persisted.append(tokens)

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    auth = CsafrontAuthManager(
        http=http,
        store=InMemoryCsafrontTokenStore(),
        initial=initial,
        on_tokens_refreshed=on_refreshed,
    )
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        responses = await asyncio.gather(*(transport.get("/devices/") for _ in range(_PARALLEL)))

    assert [r.status_code for r in responses] == [200] * _PARALLEL
    assert calls == {"refresh": 1, "smart": 1}
    assert [t.csafront_refresh_token for t in persisted] == ["rx-new"]


# ---- 403: доступ запрещён, токен не обновляется ----
async def test_403_does_not_refresh_and_raises_api_error():
    """403 у Sber — «эндпоинт недоступен аккаунту»: без refresh и retry, ApiError(403).

    Coordinator считает ApiError(403) «не поддерживается» и молча гасит опрос;
    AuthError отправил бы пользователя на повторный вход.
    """
    calls = {"gateway": 0, "auth": 0}

    def router(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith(("/smarthome/token", "/oidc/v3/token")):
            calls["auth"] += 1
            return httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600})
        calls["gateway"] += 1
        return httpx.Response(403, json={"message": "forbidden"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = _CountingTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        with pytest.raises(ApiError) as exc:
            await transport.get("/devices/indicator/values")

    assert not isinstance(exc.value, AuthError)
    assert exc.value.status_code == 403
    assert calls == {"gateway": 1, "auth": 0}
    assert store.saves == 0


# ---- In-band code 16 retry (token expired в JSON-body 200 OK) ----


async def test_inband_code_16_triggers_refresh_and_retry():
    """200 OK с `{"code": 16}` → force_refresh + retry. Второй ответ — успех."""
    state = {"first_call": True, "refreshed": False}

    def companion(req: httpx.Request) -> httpx.Response:
        state["refreshed"] = True
        return httpx.Response(200, json={"access_token": "NEW_TOK", "expires_in": 3600})

    def gateway(req: httpx.Request) -> httpx.Response:
        if state["first_call"]:
            state["first_call"] = False
            # Sber возвращает 200 OK, но с code-16 — компат-странность.
            return httpx.Response(200, json={"code": 16, "message": "token expired"})
        assert req.headers["x-auth-jwt"] == "NEW_TOK"
        return httpx.Response(200, json={"ok": True})

    def router(req: httpx.Request) -> httpx.Response:
        if "smarthome/token" in req.url.path:
            return companion(req)
        return gateway(req)

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        resp = await transport.get("/devices/")

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    assert state["refreshed"]


async def test_inband_code_16_after_retry_raises_auth_error():
    """Если retry снова code 16 — AuthError."""

    def router(req: httpx.Request) -> httpx.Response:
        if "smarthome/token" in req.url.path:
            return httpx.Response(200, json={"access_token": "NEW", "expires_in": 3600})
        return httpx.Response(200, json={"code": 16, "message": "still expired"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="OLD", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        with pytest.raises(AuthError, match="code 16"):
            await transport.get("/devices/")


async def test_inband_code_other_than_16_passes_through():
    """Code != 16 — это business error, не token expired. Retry не делаем."""

    def router(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 42, "message": "some other error"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(router))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="OK", expires_in=3600))
    sberid = SberIdTokens(access_token="SID", refresh_token="RT", expires_in=3600)
    auth = AuthManager(http=http, store=store, sberid_tokens=sberid)
    transport = HttpTransport(http=http, auth=auth)

    async with transport:
        resp = await transport.get("/devices/")

    assert resp.status_code == 200
    assert resp.json()["code"] == 42


# ---- HTTP status mapping ----
async def test_429_raises_rate_limit_with_retry_after():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "slow down"}, headers={"Retry-After": "30"})

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(RateLimitError) as exc:
            await transport.get("/devices/")
    assert exc.value.retry_after == 30.0
    assert exc.value.status_code == 429


async def test_429_without_retry_after():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="too many")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(RateLimitError) as exc:
            await transport.get("/devices/")
    assert exc.value.retry_after is None


async def test_404_raises_api_error():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"message": "device not found", "code": "NOT_FOUND"})

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(ApiError) as exc:
            await transport.get("/devices/x")
    assert exc.value.status_code == 404
    assert exc.value.code == "NOT_FOUND"
    assert "device not found" in str(exc.value)


async def test_500_raises_api_error():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(ApiError) as exc:
            await transport.get("/x")
    assert exc.value.status_code == 500


async def test_2xx_returns_response():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(204)  # No Content

    transport, _, _ = _build(h)
    async with transport:
        resp = await transport.delete("/x")
    assert resp.status_code == 204


# ---- Network errors ----
async def test_timeout_mapped_to_network_error():
    def h(req: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(NetworkError, match="Timeout"):
            await transport.get("/x")


async def test_connect_error_mapped_to_network_error():
    def h(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("DNS down")

    transport, _, _ = _build(h)
    async with transport:
        with pytest.raises(NetworkError, match="Connect failed"):
            await transport.get("/x")


# ---- Lifecycle ----
async def test_aclose_closes_underlying_http():
    def h(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    transport, _, _ = _build(h)
    await transport.aclose()
    # Повторный запрос должен упасть, потому что клиент закрыт
    with pytest.raises((RuntimeError, NetworkError)):
        await transport.get("/x")
