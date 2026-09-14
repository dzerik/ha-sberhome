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


@pytest.mark.asyncio
async def test_diagnostics_redacts_sms_login_secrets():
    """Вход по SMS хранит токены под своими именами — их тоже нужно скрыть.

    До 5.38.1 ``csafront_tokens`` уходили в файл диагностики как есть:
    рабочие токены доступа к умному дому и номер телефона оказывались в
    приложенном к issue файле.
    """
    mock_coordinator = MagicMock()
    mock_coordinator.devices = {}
    mock_coordinator.entities = {}
    mock_coordinator.client = None

    secrets = {
        "csafront_access_token": "csaf-access",
        "csafront_refresh_token": "csaf-refresh",
        "smart_home_token": "smart-home",
        "client_uuid": "0b7c2a44-uuid",
        "phone": "+79161234567",
    }
    mock_entry = MagicMock()
    mock_entry.title = "SberHome (SMS · +79161234567)"
    mock_entry.data = {
        "auth_method": "csafront",
        "csafront_tokens": {**secrets, "csafront_expires_in": 3600},
    }
    mock_entry.options = {}
    mock_entry.runtime_data = mock_coordinator

    result = await async_get_config_entry_diagnostics(None, mock_entry)

    dumped = repr(result)
    for value in secrets.values():
        assert value not in dumped, f"секрет {value!r} попал в диагностику"
    tokens = result["entry"]["data"]["csafront_tokens"]
    assert tokens["csafront_expires_in"] == 3600, "время жизни токена полезно и не секретно"
    assert result["entry"]["title"] == "SberHome (SMS · **REDACTED**)"


@pytest.mark.asyncio
async def test_diagnostics_redacts_tokens_inside_scenarios():
    """Ответы API сценариев проходят ту же маскировку, что и данные записи."""
    from unittest.mock import AsyncMock

    client = MagicMock()
    client.scenarios.get_form = AsyncMock(return_value={"fields": []})
    client.scenarios.list_system = AsyncMock(return_value=[])
    client.scenarios.list_raw = AsyncMock(
        return_value=[{"name": "Утро", "webhook": {"token": "hook-secret"}}]
    )
    mock_coordinator = MagicMock()
    mock_coordinator.devices = {}
    mock_coordinator.entities = {}
    mock_coordinator.client = client

    mock_entry = MagicMock()
    mock_entry.title = "SberHome"
    mock_entry.data = {}
    mock_entry.options = {}
    mock_entry.runtime_data = mock_coordinator

    result = await async_get_config_entry_diagnostics(None, mock_entry)

    assert "hook-secret" not in repr(result)
    assert result["scenarios"]["user_scenarios"][0]["name"] == "Утро"
