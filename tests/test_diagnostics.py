"""Tests for the SberHome diagnostics."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from custom_components.sberhome.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import MOCK_DEVICE_LIGHT, MOCK_TOKEN


@pytest.mark.asyncio
async def test_diagnostics_output():
    from custom_components.sberhome.aiosber.dto.device import DeviceDto

    mock_coordinator = MagicMock()
    dto = DeviceDto.from_dict(MOCK_DEVICE_LIGHT)
    mock_coordinator.devices = {"device_light_1": dto}
    mock_coordinator.entities = {"device_light_1": []}

    mock_entry = MagicMock()
    mock_entry.title = "SberHome"
    mock_entry.data = {"token": MOCK_TOKEN}
    mock_entry.options = {"scan_interval": 30}
    mock_entry.runtime_data = mock_coordinator

    result = await async_get_config_entry_diagnostics(None, mock_entry)

    assert result["devices_count"] == 1
    assert "device_light_1" in result["devices"]
    # name в DTO — это "name" поле верхнего уровня (string), не nested dict.
    # MOCK_DEVICE_LIGHT.name = {"name": "Test Light"} → DTO.name = None.
    assert result["entry"]["data"]["token"] == "**REDACTED**"
    assert result["entry"]["options"]["scan_interval"] == 30


@pytest.mark.asyncio
async def test_diagnostics_redacts_token_key():
    mock_coordinator = MagicMock()
    mock_coordinator.devices = {}
    mock_coordinator.entities = {}

    mock_entry = MagicMock()
    mock_entry.title = "SberHome"
    mock_entry.data = {
        "token": {"access_token": "secret", "scope": "openid"},
        "other_key": "visible",
    }
    mock_entry.options = {}
    mock_entry.runtime_data = mock_coordinator

    result = await async_get_config_entry_diagnostics(None, mock_entry)

    # "token" key is in TO_REDACT, so entire value is redacted
    assert result["entry"]["data"]["token"] == "**REDACTED**"
    assert result["entry"]["data"]["other_key"] == "visible"


@pytest.mark.asyncio
async def test_diagnostics_no_coordinator_data():
    mock_entry = MagicMock()
    mock_entry.title = "SberHome"
    mock_entry.data = {"token": "secret"}
    mock_entry.options = {}
    mock_entry.runtime_data = None

    result = await async_get_config_entry_diagnostics(None, mock_entry)

    assert result["devices_count"] == 0
    assert result["devices"] == {}
