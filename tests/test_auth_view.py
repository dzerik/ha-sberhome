"""Tests for the SberHome auth views."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp.test_utils import make_mocked_request

import custom_components.sberhome.auth_view as auth_view_module
from custom_components.sberhome.auth_view import (
    SberAuthCallbackView,
    SberAuthStartView,
)


@pytest.fixture(autouse=True)
def reset_template_cache():
    """Reset the cached auth page template between tests."""
    auth_view_module._AUTH_PAGE_TEMPLATE = None
    yield
    auth_view_module._AUTH_PAGE_TEMPLATE = None


@pytest.mark.asyncio
async def test_start_view_returns_html():
    """Test that the start view returns HTML with flow_id and auth_url."""
    view = SberAuthStartView()
    request = make_mocked_request(
        "GET",
        "/auth/sberhome?flow_id=abc123&auth_url=https%3A%2F%2Fexample.com",
    )

    mock_hass = MagicMock()
    mock_hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *args: fn(*args))
    request.app["hass"] = mock_hass

    response = await view.get(request)

    assert response.content_type == "text/html"
    body = response.text
    assert "abc123" in body
    assert "https://example.com" in body
    assert "companionapp://" in body


def _make_callback_request(json_data, hass=None):
    """Create a mocked POST request with JSON body for callback view."""
    request = make_mocked_request(
        "POST",
        "/auth/sberhome/callback",
        headers={"Content-Type": "application/json"},
    )
    request.json = AsyncMock(return_value=json_data)
    if hass is not None:
        request.app["hass"] = hass
    return request


@pytest.mark.asyncio
async def test_callback_view_success():
    """Test successful callback authorizes and configures the flow."""
    from custom_components.sberhome.auth_state import PendingFlow

    view = SberAuthCallbackView()

    mock_client = AsyncMock()
    mock_client.authorize_by_url = AsyncMock(return_value=True)

    mock_hass = MagicMock()
    mock_hass.config_entries.flow.async_configure = AsyncMock()

    request = _make_callback_request(
        {"flow_id": "test-flow", "url": "companionapp://host?code=abc&state=xyz"},
        hass=mock_hass,
    )

    with patch(
        "custom_components.sberhome.auth_state.pending_auth_flows",
        {"test-flow": PendingFlow(client=mock_client)},
    ):
        response = await view.post(request)

    assert response.status == 200
    mock_client.authorize_by_url.assert_awaited_once_with("companionapp://host?code=abc&state=xyz")
    mock_hass.config_entries.flow.async_configure.assert_awaited_once()


@pytest.mark.asyncio
async def test_callback_view_missing_flow_id():
    """Test callback with missing flow_id returns 400."""
    view = SberAuthCallbackView()
    request = _make_callback_request({"url": "companionapp://host?code=abc"})

    response = await view.post(request)
    assert response.status == 400


@pytest.mark.asyncio
async def test_callback_view_invalid_url():
    """Test callback with non-companionapp URL returns 400."""
    view = SberAuthCallbackView()
    request = _make_callback_request({"flow_id": "test-flow", "url": "https://evil.com"})

    response = await view.post(request)
    assert response.status == 400


@pytest.mark.asyncio
async def test_callback_view_url_without_code():
    """Test callback with URL missing code= parameter returns 400."""
    view = SberAuthCallbackView()
    request = _make_callback_request(
        {
            "flow_id": "test-flow",
            "url": "companionapp://host&scope=openid&state=xxx",
        }
    )

    response = await view.post(request)
    assert response.status == 400


@pytest.mark.asyncio
async def test_callback_view_flow_not_found():
    """Test callback returns 404 when flow is not in pending_auth_flows."""
    view = SberAuthCallbackView()
    request = _make_callback_request(
        {"flow_id": "gone-flow", "url": "companionapp://host?code=abc"},
    )

    with patch("custom_components.sberhome.auth_state.pending_auth_flows", {}):
        response = await view.post(request)

    assert response.status == 404


@pytest.mark.asyncio
async def test_callback_view_auth_failed():
    """Test callback returns 401 when authorize_by_url fails."""
    from custom_components.sberhome.auth_state import PendingFlow

    view = SberAuthCallbackView()

    mock_client = AsyncMock()
    mock_client.authorize_by_url = AsyncMock(return_value=False)

    request = _make_callback_request(
        {"flow_id": "test-flow", "url": "companionapp://host?code=expired"},
    )

    with patch(
        "custom_components.sberhome.auth_state.pending_auth_flows",
        {"test-flow": PendingFlow(client=mock_client)},
    ):
        response = await view.post(request)

    assert response.status == 401
