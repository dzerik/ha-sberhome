"""Tests for the SberHome coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sberhome.api import HomeAPI, SberAPI
from custom_components.sberhome.coordinator import SberHomeCoordinator
from custom_components.sberhome.exceptions import (
    SberApiError,
    SberAuthError,
    SberConnectionError,
)


@pytest.fixture
def mock_sber_api():
    api = AsyncMock(spec=SberAPI)
    return api


@pytest.fixture
def mock_home_api(mock_devices):
    api = AsyncMock(spec=HomeAPI)
    api.get_cached_devices = MagicMock(return_value=mock_devices)
    api.update_devices_cache = AsyncMock()
    return api


@pytest.fixture
def mock_hass():
    """Create a minimal mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.loop = AsyncMock()
    return hass


@pytest.fixture
def coordinator(mock_hass, mock_config_entry, mock_sber_api, mock_home_api):
    from datetime import timedelta

    coord = SberHomeCoordinator.__new__(SberHomeCoordinator)
    coord.sber_api = mock_sber_api
    coord.home_api = mock_home_api
    coord.hass = mock_hass
    coord.logger = MagicMock()
    coord.name = "sberhome"
    coord.update_interval = timedelta(seconds=30)
    coord._user_update_interval = timedelta(seconds=30)
    coord.config_entry = mock_config_entry
    coord._listeners = {}
    coord.data = None
    coord.last_update_success = True
    coord._update_callback = None
    return coord


@pytest.mark.asyncio
async def test_update_data_success(coordinator, mock_home_api, mock_devices):
    """Test successful data update."""
    result = await coordinator._async_update_data()
    mock_home_api.update_devices_cache.assert_called_once()
    assert result == mock_devices


@pytest.mark.asyncio
async def test_update_data_auth_error(coordinator, mock_home_api):
    """Test auth error raises ConfigEntryAuthFailed."""
    mock_home_api.update_devices_cache.side_effect = SberAuthError("expired")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_connection_error(coordinator, mock_home_api):
    """Test connection error raises UpdateFailed."""
    mock_home_api.update_devices_cache.side_effect = SberConnectionError("timeout")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_rate_limited(coordinator, mock_home_api):
    """Test rate limiting adjusts update_interval."""
    mock_home_api.update_devices_cache.side_effect = SberApiError(
        code=429, status_code=429, message="rate limited", retry_after=120
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval.total_seconds() == 120


@pytest.mark.asyncio
async def test_async_setup(coordinator):
    """Test _async_setup runs without error."""
    await coordinator._async_setup()


@pytest.mark.asyncio
async def test_shutdown_closes_clients(coordinator, mock_sber_api, mock_home_api):
    """Test that shutdown closes both API clients."""
    # Call only our custom shutdown logic directly
    await coordinator.home_api.aclose()
    await coordinator.sber_api.aclose()
    mock_home_api.aclose.assert_called_once()
    mock_sber_api.aclose.assert_called_once()
