"""Tests for HA-side `api.py` shim над aiosber.

Старые тесты (patching _client.request, _gateway_token_exp tracking, _get_ssl_context
module global) удалены — соответствующая старая реализация ушла в PR #5.

Новые тесты:
- Используют httpx.MockTransport как aiosber-тесты.
- Проверяют публичный интерфейс HomeAPI/SberAPI (на котором завязаны платформы).
- Структурное тестирование внутренностей минимизировано.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from custom_components.sberhome.api import (
    COMMAND_RETRY_DELAY,
    HomeAPI,
    SberAPI,
    _legacy_state_to_attr,
    _parse_jwt_exp,
)
from custom_components.sberhome.exceptions import (
    SberApiError,
    SberConnectionError,
)
from custom_components.sberhome.utils import extract_devices
from tests.conftest import MOCK_DEVICE_TREE


# ============== utils ==============
def test_extract_devices_nested():
    devices = extract_devices(MOCK_DEVICE_TREE)
    assert len(devices) == 3
    assert "device_light_1" in devices
    assert "device_ledstrip_1" in devices
    assert "device_switch_1" in devices


def test_extract_devices_flat():
    tree = {"devices": [{"id": "a"}, {"id": "b"}], "children": []}
    devices = extract_devices(tree)
    assert len(devices) == 2


# ============== _parse_jwt_exp (legacy helper) ==============
class TestParseJwtExp:
    def test_valid_jwt(self):
        import base64

        payload = (
            base64.urlsafe_b64encode(json.dumps({"exp": 1700000000}).encode())
            .rstrip(b"=")
            .decode()
        )
        assert _parse_jwt_exp(f"h.{payload}.s") == 1700000000

    def test_jwt_without_exp(self):
        import base64

        payload = (
            base64.urlsafe_b64encode(json.dumps({"sub": "user"}).encode())
            .rstrip(b"=")
            .decode()
        )
        assert _parse_jwt_exp(f"h.{payload}.s") is None

    def test_invalid_jwt(self):
        assert _parse_jwt_exp("not-a-jwt") is None
        assert _parse_jwt_exp("") is None
        assert _parse_jwt_exp("a.not-base64!.c") is None


# ============== _legacy_state_to_attr ==============
class TestLegacyStateToAttr:
    """Legacy {"key": ..., "X_value": ...} → AttributeValueDto."""

    def test_bool(self):
        attr = _legacy_state_to_attr({"key": "on_off", "bool_value": True})
        assert attr.bool_value is True
        assert attr.key == "on_off"

    def test_integer(self):
        attr = _legacy_state_to_attr({"key": "x", "integer_value": 42})
        assert attr.integer_value == 42

    def test_float(self):
        attr = _legacy_state_to_attr({"key": "t", "float_value": 23.5})
        assert attr.float_value == 23.5

    def test_string(self):
        attr = _legacy_state_to_attr({"key": "n", "string_value": "abc"})
        assert attr.string_value == "abc"

    def test_enum(self):
        attr = _legacy_state_to_attr({"key": "m", "enum_value": "auto"})
        assert attr.enum_value == "auto"

    def test_color_legacy_hsv_short_form(self):
        """Legacy формат {h, s, v} мапится в правильное {hue, saturation, brightness}."""
        attr = _legacy_state_to_attr({
            "key": "c",
            "color_value": {"h": 120, "s": 50, "v": 80},
        })
        assert attr.color_value is not None
        assert attr.color_value.hue == 120
        assert attr.color_value.saturation == 50
        assert attr.color_value.brightness == 80

    def test_color_modern_long_form(self):
        attr = _legacy_state_to_attr({
            "key": "c",
            "color_value": {"hue": 200, "saturation": 90, "brightness": 70},
        })
        assert attr.color_value is not None
        assert attr.color_value.hue == 200


# ============== SberAPI ==============
class TestSberAPI:
    def test_init_without_token(self):
        api = SberAPI()
        assert api.token is None

    def test_init_with_token(self):
        token = {
            "access_token": "test",
            "refresh_token": "rt",
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        api = SberAPI(token=token)
        # to_dict round-trip — поля могут добавиться (id_token, scope, obtained_at)
        assert api.token is not None
        assert api.token["access_token"] == "test"

    def test_create_authorization_url(self):
        api = SberAPI()
        url = api.create_authorization_url()
        # OAuth host: online.sberbank.ru (id.sber.ru отвергает наш CLIENT_ID).
        assert "online.sberbank.ru" in url
        assert "code_challenge=" in url
        assert "code_challenge_method=S256" in url
        assert "redirect_uri=" in url

    @pytest.mark.asyncio
    async def test_authorize_by_url_invalid_returns_false(self):
        api = SberAPI()
        api.create_authorization_url()
        # URL без кода
        assert await api.authorize_by_url("companionapp://host?error=denied") is False

    @pytest.mark.asyncio
    async def test_authorize_by_url_without_create_returns_false(self):
        """Без вызова create_authorization_url() (нет PKCE state)."""
        api = SberAPI()
        assert await api.authorize_by_url("companionapp://host?code=x&state=s") is False

    @pytest.mark.asyncio
    async def test_aclose_safe_without_init(self):
        api = SberAPI()
        await api.aclose()  # http не создан — no-op


# ============== HomeAPI ==============
class TestHomeAPI:
    """HomeAPI tests через httpx.MockTransport (без patch.object)."""

    @pytest.fixture
    async def home_api(self):
        """HomeAPI с заранее установленным companion-токеном.

        Подменяем SberAPI._http и помещаем готовый CompanionTokens — это
        позволяет HomeAPI._ensure_client() построить SberClient без вызова
        реального companion endpoint.
        """
        from custom_components.sberhome.aiosber.auth import CompanionTokens

        sber = SberAPI()
        sber._companion = CompanionTokens(access_token="TEST_TOK", expires_in=3600)
        # Stub httpx с MockTransport — всё перехватывается тестами через side_effect.
        sber._http = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(404))
        )
        api = HomeAPI(sber)
        yield api
        await api.aclose()
        await sber.aclose()

    @pytest.mark.asyncio
    async def test_request_success(self, home_api):
        # Подменяем mock_transport на success-handler
        home_api._sber._http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"result": "ok"})
            )
        )
        result = await home_api.request("GET", "/test")
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_request_rate_limited(self, home_api):
        home_api._sber._http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    429, json={"message": "slow down"}, headers={"Retry-After": "30"}
                )
            )
        )
        with pytest.raises(SberApiError) as exc:
            await home_api.request("GET", "/test")
        assert exc.value.code == 429
        assert exc.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_request_api_error(self, home_api):
        home_api._sber._http = httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(
                    400, json={"code": 3, "message": "bad request"}
                )
            )
        )
        with pytest.raises(SberApiError) as exc:
            await home_api.request("GET", "/test")
        # ApiError из aiosber мапится — code может быть 3 или -1 (если int parsing)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_request_connection_error(self, home_api):
        def handler(req: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection failed")

        home_api._sber._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        with pytest.raises(SberConnectionError):
            await home_api.request("GET", "/test")

    @pytest.mark.asyncio
    async def test_set_device_state_retries_on_connection_error(self, home_api):
        """set_device_state делает один retry на сетевой ошибке."""
        home_api._cached_devices = {
            "dev1": {"desired_state": [{"key": "on_off", "bool_value": False}]}
        }
        call_count = 0

        async def mock_inner(device_id, state):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise SberConnectionError("network error")

        with (
            patch.object(home_api, "_set_device_state_inner", side_effect=mock_inner),
            patch(
                "custom_components.sberhome.api.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
        ):
            await home_api.set_device_state(
                "dev1", [{"key": "on_off", "bool_value": True}]
            )
            mock_sleep.assert_called_once_with(COMMAND_RETRY_DELAY)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_set_device_state_merges_cache(self, home_api):
        """После успешной команды desired_state локального кеша обновляется."""
        home_api._cached_devices = {
            "dev1": {
                "desired_state": [
                    {"key": "on_off", "bool_value": False},
                    {"key": "light_brightness", "integer_value": 100},
                ]
            }
        }
        # Mock-transport успешный
        home_api._sber._http = httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={"result": {}}))
        )
        await home_api.set_device_state(
            "dev1", [{"key": "on_off", "bool_value": True}]
        )
        state = home_api._cached_devices["dev1"]["desired_state"]
        on_off = next(s for s in state if s["key"] == "on_off")
        assert on_off["bool_value"] is True
        # Brightness не тронут
        brightness = next(s for s in state if s["key"] == "light_brightness")
        assert brightness["integer_value"] == 100

    @pytest.mark.asyncio
    async def test_aclose(self, home_api):
        await home_api.aclose()  # safe: no-op для http (закроет SberAPI)

    @pytest.mark.asyncio
    async def test_update_token_no_op_when_fresh(self, home_api):
        """update_token не должен делать сетевой запрос, если companion свеж."""
        # Если бы делал HTTP запрос — упал бы 404 (default handler).
        await home_api.update_token()  # не должно поднять
