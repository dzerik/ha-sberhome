"""Tests for HATokenStore — companion-token persistence через ConfigEntry.data."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from custom_components.sberhome._ha_token_store import (
    CONF_COMPANION_TOKENS,
    HATokenStore,
)
from custom_components.sberhome.aiosber.auth import CompanionTokens


@pytest.fixture
def mock_hass() -> MagicMock:
    hass = MagicMock(spec=HomeAssistant)
    hass.config_entries = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


@pytest.fixture
def mock_entry() -> MagicMock:
    entry = MagicMock(spec=ConfigEntry)
    entry.data = {"token": {"access_token": "sber_access"}}
    return entry


@pytest.fixture
def store(mock_hass: MagicMock, mock_entry: MagicMock) -> HATokenStore:
    return HATokenStore(mock_hass, mock_entry)


async def test_load_returns_none_when_no_data(store: HATokenStore) -> None:
    assert await store.load() is None


async def test_load_returns_none_when_empty_dict(
    mock_hass: MagicMock, mock_entry: MagicMock
) -> None:
    mock_entry.data = {"token": {}, CONF_COMPANION_TOKENS: {}}
    store = HATokenStore(mock_hass, mock_entry)
    assert await store.load() is None


async def test_load_deserializes_existing_tokens(
    mock_hass: MagicMock, mock_entry: MagicMock
) -> None:
    obtained = time.time() - 100
    mock_entry.data = {
        "token": {},
        CONF_COMPANION_TOKENS: {
            "access_token": "comp_token",
            "refresh_token": "comp_refresh",
            "token_type": "Bearer",
            "expires_in": 86400,
            "obtained_at": obtained,
        },
    }
    store = HATokenStore(mock_hass, mock_entry)
    loaded = await store.load()
    assert loaded is not None
    assert loaded.access_token == "comp_token"
    assert loaded.refresh_token == "comp_refresh"
    assert loaded.expires_in == 86400
    assert loaded.obtained_at == obtained


async def test_save_persists_via_async_update_entry(
    store: HATokenStore, mock_hass: MagicMock, mock_entry: MagicMock
) -> None:
    tokens = CompanionTokens(
        access_token="new_token",
        refresh_token="new_refresh",
        expires_in=3600,
    )

    await store.save(tokens)

    mock_hass.config_entries.async_update_entry.assert_called_once()
    call_kwargs = mock_hass.config_entries.async_update_entry.call_args
    assert call_kwargs.args[0] is mock_entry
    new_data = call_kwargs.kwargs["data"]
    # сохранили companion блок
    assert CONF_COMPANION_TOKENS in new_data
    # не потеряли существующие ключи
    assert new_data["token"] == {"access_token": "sber_access"}
    # данные сериализованы
    assert new_data[CONF_COMPANION_TOKENS]["access_token"] == "new_token"
    assert new_data[CONF_COMPANION_TOKENS]["refresh_token"] == "new_refresh"


async def test_save_then_load_roundtrip(
    mock_hass: MagicMock, mock_entry: MagicMock
) -> None:
    """Проверяем, что save→load возвращает эквивалентные токены."""
    store = HATokenStore(mock_hass, mock_entry)
    tokens = CompanionTokens(
        access_token="roundtrip",
        refresh_token="r",
        expires_in=7200,
    )

    # эмулируем persist через side_effect: обновляем entry.data
    def _fake_update(entry: ConfigEntry, *, data: dict) -> None:
        entry.data = data

    mock_hass.config_entries.async_update_entry.side_effect = _fake_update

    await store.save(tokens)
    loaded = await store.load()

    assert loaded is not None
    assert loaded.access_token == tokens.access_token
    assert loaded.refresh_token == tokens.refresh_token
    assert loaded.expires_in == tokens.expires_in


async def test_clear_removes_companion_tokens_only(
    mock_hass: MagicMock, mock_entry: MagicMock
) -> None:
    mock_entry.data = {
        "token": {"access_token": "sber"},
        "other": "preserved",
        CONF_COMPANION_TOKENS: {"access_token": "to_remove"},
    }
    store = HATokenStore(mock_hass, mock_entry)

    await store.clear()

    call_kwargs = mock_hass.config_entries.async_update_entry.call_args
    new_data = call_kwargs.kwargs["data"]
    assert CONF_COMPANION_TOKENS not in new_data
    assert new_data["token"] == {"access_token": "sber"}
    assert new_data["other"] == "preserved"


async def test_clear_when_no_companion_tokens(
    store: HATokenStore, mock_hass: MagicMock, mock_entry: MagicMock
) -> None:
    """clear() безопасно вызывается, даже если companion-токенов нет."""
    await store.clear()
    mock_hass.config_entries.async_update_entry.assert_called_once()
    new_data = mock_hass.config_entries.async_update_entry.call_args.kwargs["data"]
    assert CONF_COMPANION_TOKENS not in new_data
