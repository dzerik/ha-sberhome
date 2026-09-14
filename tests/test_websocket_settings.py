"""WS настроек и экспорта/импорта конфигурации панели."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sberhome.settings import SETTINGS_DEFAULTS, SETTINGS_LIMITS
from custom_components.sberhome.websocket_api import settings as ws_settings

MODULE = "custom_components.sberhome.websocket_api.settings"


@pytest.fixture
def connection() -> MagicMock:
    return MagicMock()


def _entry(options: dict) -> MagicMock:
    entry = MagicMock()
    entry.options = options
    return entry


def _hass() -> MagicMock:
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()
    return hass


def test_get_settings_returns_values_defaults_and_limits(connection: MagicMock) -> None:
    with patch(f"{MODULE}.get_config_entry", return_value=_entry({"scan_interval": 90})):
        ws_settings.ws_get_settings(_hass(), connection, {"id": 1})
    result = connection.send_result.call_args[0][1]
    assert result["settings"] == {**SETTINGS_DEFAULTS, "scan_interval": 90}
    assert result["defaults"] == SETTINGS_DEFAULTS
    assert result["limits"] == SETTINGS_LIMITS


@pytest.mark.asyncio
async def test_update_settings_persists_valid_values(connection: MagicMock) -> None:
    hass = _hass()
    entry = _entry({"enabled_device_uids": ["a"]})
    with (
        patch(f"{MODULE}.get_config_entry", return_value=entry),
        patch(f"{MODULE}.get_coordinator", return_value=MagicMock()),
    ):
        await ws_settings.ws_update_settings.__wrapped__(
            hass, connection, {"id": 1, "settings": {"scan_interval": 120, "command_timeout": 15}}
        )
    new_options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert new_options == {
        "enabled_device_uids": ["a"],
        "scan_interval": 120,
        "command_timeout": 15.0,
    }
    connection.send_result.assert_called_once()


@pytest.mark.asyncio
async def test_update_settings_rejects_the_whole_request(connection: MagicMock) -> None:
    hass = _hass()
    with (
        patch(f"{MODULE}.get_config_entry", return_value=_entry({})),
        patch(f"{MODULE}.get_coordinator", return_value=MagicMock()),
    ):
        await ws_settings.ws_update_settings.__wrapped__(
            hass,
            connection,
            {"id": 1, "settings": {"scan_interval": 120, "command_timeout": "soon"}},
        )
    hass.config_entries.async_update_entry.assert_not_called()
    assert connection.send_error.call_args[0][1] == "invalid_settings"


def test_export_config(connection: MagicMock) -> None:
    entry = _entry(
        {"enabled_device_uids": ["uid-1", "uid-2"], "scan_interval": 60, "selection_mirror": ["x"]}
    )
    with patch(f"{MODULE}.get_config_entry", return_value=entry):
        ws_settings.ws_export_config(_hass(), connection, {"id": 1})
    result = connection.send_result.call_args[0][1]
    assert result == {
        "format": "sberhome-config",
        "version": 1,
        "enabled_device_uids": ["uid-1", "uid-2"],
        "settings": {**SETTINGS_DEFAULTS, "scan_interval": 60},
    }


@pytest.mark.asyncio
async def test_import_config_applies_selection_and_settings(connection: MagicMock) -> None:
    hass = _hass()
    entry = _entry({"scan_interval": 30})
    coord = MagicMock()
    coord.async_import_selection = AsyncMock()
    config = {
        "format": "sberhome-config",
        "version": 1,
        "enabled_device_uids": ["uid-9"],
        "settings": {"scan_interval": 300, "devtools_buffer_size": 50},
    }
    with (
        patch(f"{MODULE}.get_config_entry", return_value=entry),
        patch(f"{MODULE}.get_coordinator", return_value=coord),
    ):
        await ws_settings.ws_import_config.__wrapped__(
            hass, connection, {"id": 1, "config": config}
        )
    new_options = hass.config_entries.async_update_entry.call_args.kwargs["options"]
    assert new_options == {"scan_interval": 300, "devtools_buffer_size": 50}
    coord.async_import_selection.assert_awaited_once_with(["uid-9"])
    assert connection.send_result.call_args[0][1] == {"success": True, "devices": 1}


@pytest.mark.parametrize(
    "config",
    [
        {"format": "other", "version": 1, "enabled_device_uids": [], "settings": {}},
        {"format": "sberhome-config", "version": 2, "enabled_device_uids": [], "settings": {}},
        {"format": "sberhome-config", "version": 1, "enabled_device_uids": [5], "settings": {}},
        {
            "format": "sberhome-config",
            "version": 1,
            "enabled_device_uids": [],
            "settings": {"scan_interval": 1},
        },
    ],
)
@pytest.mark.asyncio
async def test_import_config_rejects_invalid_files_without_changes(
    connection: MagicMock, config: dict
) -> None:
    hass = _hass()
    coord = MagicMock()
    coord.async_import_selection = AsyncMock()
    with (
        patch(f"{MODULE}.get_config_entry", return_value=_entry({})),
        patch(f"{MODULE}.get_coordinator", return_value=coord),
    ):
        await ws_settings.ws_import_config.__wrapped__(
            hass, connection, {"id": 1, "config": config}
        )
    hass.config_entries.async_update_entry.assert_not_called()
    coord.async_import_selection.assert_not_called()
    assert connection.send_error.call_args[0][1] == "invalid_config"


@pytest.mark.asyncio
async def test_force_refresh_restarts_stopped_background_polls(connection: MagicMock) -> None:
    """Совет «нажмите Обновить» в состоянии интеграции должен действительно работать."""
    coord = MagicMock()
    coord.async_request_refresh = AsyncMock()
    coord.async_refresh_staros = AsyncMock()
    order: list[str] = []
    coord.reset_background_polls.side_effect = lambda: order.append("reset")
    coord.async_request_refresh.side_effect = lambda: order.append("refresh")
    with patch(f"{MODULE}.get_coordinator", return_value=coord):
        await ws_settings.ws_force_refresh.__wrapped__(_hass(), connection, {"id": 1})
    assert order == ["reset", "refresh"], (
        "polls must be re-enabled before the refresh that runs them"
    )
