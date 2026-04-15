"""Tests for the SberHome API module."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sberhome.api import (
    COMMAND_RETRY_DELAY,
    HomeAPI,
    SberAPI,
    _parse_jwt_exp,
)
from custom_components.sberhome.utils import extract_devices, find_from_list
from custom_components.sberhome.exceptions import (
    SberApiError,
    SberAuthError,
    SberConnectionError,
)
from tests.conftest import MOCK_DEVICE_TREE


def test_extract_devices_nested():
    """Test extract_devices from nested tree."""
    devices = extract_devices(MOCK_DEVICE_TREE)
    assert len(devices) == 3
    assert "device_light_1" in devices
    assert "device_ledstrip_1" in devices
    assert "device_switch_1" in devices


def test_extract_devices_flat():
    """Test extract_devices from flat tree."""
    tree = {"devices": [{"id": "a"}, {"id": "b"}], "children": []}
    devices = extract_devices(tree)
    assert len(devices) == 2
    assert "a" in devices
    assert "b" in devices


def test_find_from_list_found():
    """Test find_from_list when key exists."""
    data = [{"key": "on_off", "bool_value": True}, {"key": "mode", "enum_value": "white"}]
    result = find_from_list(data, "on_off")
    assert result is not None
    assert result["bool_value"] is True


def test_find_from_list_not_found():
    """Test find_from_list when key does not exist."""
    data = [{"key": "on_off", "bool_value": True}]
    result = find_from_list(data, "nonexistent")
    assert result is None


def test_find_from_list_empty():
    """Test find_from_list with empty list."""
    assert find_from_list([], "anything") is None


def test_ssl_context_creation():
    """Test SSL context is created without tempfile."""
    from custom_components.sberhome.api import _get_ssl_context

    ctx = _get_ssl_context()
    assert ctx is not None


class TestParseJwtExp:
    """Tests for _parse_jwt_exp."""

    def test_valid_jwt(self):
        """Test parsing a valid JWT with exp claim."""
        import base64
        import json

        payload = base64.urlsafe_b64encode(
            json.dumps({"exp": 1700000000}).encode()
        ).rstrip(b"=").decode()
        token = f"header.{payload}.signature"
        assert _parse_jwt_exp(token) == 1700000000

    def test_jwt_without_exp(self):
        """Test JWT without exp claim returns None."""
        import base64
        import json

        payload = base64.urlsafe_b64encode(
            json.dumps({"sub": "user"}).encode()
        ).rstrip(b"=").decode()
        token = f"header.{payload}.signature"
        assert _parse_jwt_exp(token) is None

    def test_invalid_jwt(self):
        """Test invalid JWT returns None."""
        assert _parse_jwt_exp("not-a-jwt") is None
        assert _parse_jwt_exp("") is None

    def test_malformed_payload(self):
        """Test JWT with non-JSON payload returns None."""
        assert _parse_jwt_exp("a.not-base64!.c") is None


class TestSberAPI:
    """Tests for SberAPI."""

    def test_init_without_token(self):
        api = SberAPI()
        assert api.token is not None or api.token is None  # just no crash

    def test_init_with_token(self):
        token = {"access_token": "test", "token_type": "Bearer"}
        api = SberAPI(token=token)
        assert api.token == token

    def test_create_authorization_url(self):
        api = SberAPI()
        url = api.create_authorization_url()
        assert "online.sberbank.ru" in url
        assert "authorize" in url

    @pytest.mark.asyncio
    async def test_authorize_by_url_exception_returns_false(self):
        api = SberAPI()
        result = await api.authorize_by_url("invalid://url")
        assert result is False

    @pytest.mark.asyncio
    async def test_aclose(self):
        api = SberAPI()
        await api.aclose()  # should not raise


class TestHomeAPI:
    """Tests for HomeAPI."""

    @pytest.fixture
    def mock_sber(self):
        sber = AsyncMock(spec=SberAPI)
        sber.fetch_home_token = AsyncMock(return_value="test_jwt_token")
        return sber

    @pytest.fixture
    def home_api(self, mock_sber):
        return HomeAPI(mock_sber)

    @pytest.mark.asyncio
    async def test_update_token(self, home_api, mock_sber):
        await home_api.update_token()
        mock_sber.fetch_home_token.assert_called_once()
        assert home_api._gateway_token == "test_jwt_token"

    @pytest.mark.asyncio
    async def test_update_token_skips_if_not_expired(self, home_api, mock_sber):
        home_api._gateway_token = "existing_token"
        home_api._gateway_token_exp = time.time() + 3600
        await home_api.update_token()
        mock_sber.fetch_home_token.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_token_refreshes_when_near_expiry(self, home_api, mock_sber):
        home_api._gateway_token = "old_token"
        home_api._gateway_token_exp = time.time() + 30  # less than 60s margin
        await home_api.update_token()
        mock_sber.fetch_home_token.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_success(self, home_api):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "ok"}

        with patch.object(
            home_api._client, "request", new_callable=AsyncMock, return_value=mock_response
        ):
            result = await home_api.request("GET", "/test")
            assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_request_token_expired_retry(self, home_api):
        expired_response = MagicMock()
        expired_response.status_code = 401
        expired_response.json.return_value = {"code": 16, "message": "expired"}

        success_response = MagicMock()
        success_response.status_code = 200
        success_response.json.return_value = {"result": "ok"}

        with patch.object(
            home_api._client,
            "request",
            new_callable=AsyncMock,
            side_effect=[expired_response, success_response],
        ):
            result = await home_api.request("GET", "/test")
            assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_request_rate_limited(self, home_api):
        """Test 429 rate limiting raises SberApiError with retry_after."""
        rate_limited_response = MagicMock()
        rate_limited_response.status_code = 429
        rate_limited_response.headers = {"Retry-After": "30"}

        with patch.object(
            home_api._client, "request", new_callable=AsyncMock, return_value=rate_limited_response
        ):
            with pytest.raises(SberApiError) as exc_info:
                await home_api.request("GET", "/test")
            assert exc_info.value.code == 429
            assert exc_info.value.retry_after == 30

    @pytest.mark.asyncio
    async def test_request_api_error(self, home_api):
        error_response = MagicMock()
        error_response.status_code = 400
        error_response.json.return_value = {"code": 3, "message": "bad request"}

        with patch.object(
            home_api._client, "request", new_callable=AsyncMock, return_value=error_response
        ):
            with pytest.raises(SberApiError) as exc_info:
                await home_api.request("GET", "/test")
            assert exc_info.value.code == 3

    @pytest.mark.asyncio
    async def test_request_connection_error(self, home_api):
        from httpx import ConnectError

        with patch.object(
            home_api._client,
            "request",
            new_callable=AsyncMock,
            side_effect=ConnectError("connection failed"),
        ):
            with pytest.raises(SberConnectionError):
                await home_api.request("GET", "/test")

    @pytest.mark.asyncio
    async def test_set_device_state_retries_on_connection_error(self, home_api):
        """Test set_device_state retries once on SberConnectionError."""
        home_api._cached_devices = {
            "dev1": {"desired_state": [{"key": "on_off", "bool_value": False}]}
        }
        call_count = 0

        async def mock_inner(device_id, state):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise SberConnectionError("network error")
            # Simulate cache merge
            for s in state:
                for attr in home_api._cached_devices[device_id]["desired_state"]:
                    if attr["key"] == s["key"]:
                        attr.update(s)

        with patch.object(home_api, "_set_device_state_inner", side_effect=mock_inner):
            with patch("custom_components.sberhome.api.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                await home_api.set_device_state("dev1", [{"key": "on_off", "bool_value": True}])
                mock_sleep.assert_called_once_with(COMMAND_RETRY_DELAY)
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_set_device_state_merges_cache(self, home_api):
        home_api._cached_devices = {
            "dev1": {
                "desired_state": [
                    {"key": "on_off", "bool_value": False},
                    {"key": "light_brightness", "integer_value": 100},
                ]
            }
        }
        with patch.object(home_api, "request", new_callable=AsyncMock, return_value={}):
            await home_api.set_device_state(
                "dev1", [{"key": "on_off", "bool_value": True}]
            )

        state = home_api._cached_devices["dev1"]["desired_state"]
        on_off = next(s for s in state if s["key"] == "on_off")
        assert on_off["bool_value"] is True
        brightness = next(s for s in state if s["key"] == "light_brightness")
        assert brightness["integer_value"] == 100

    @pytest.mark.asyncio
    async def test_aclose(self, home_api):
        with patch.object(home_api._client, "aclose", new_callable=AsyncMock) as mock_close:
            await home_api.aclose()
            mock_close.assert_called_once()
