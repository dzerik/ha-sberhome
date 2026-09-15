"""Настройки применяются на лету; выбор устройств по-прежнему перезагружает запись."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome import _async_entry_updated
from custom_components.sberhome.command_tracker import CommandTracker
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.coordinator import SberHomeCoordinator
from custom_components.sberhome.schema_validator import ValidationCollector
from custom_components.sberhome.state_diff import DiffCollector
from custom_components.sberhome.ws_devtools import WsDevToolsRecorder


def _coordinator() -> SberHomeCoordinator:
    coord = SberHomeCoordinator.__new__(SberHomeCoordinator)
    coord.ws_devtools = WsDevToolsRecorder(maxlen=100)
    coord._ws_log = coord.ws_devtools.log
    coord.diff_collector = DiffCollector(maxlen=200)
    coord.validation_collector = ValidationCollector(maxlen=500)
    coord.command_tracker = CommandTracker(maxlen=200, command_timeout=10.0)
    coord._user_update_interval = timedelta(seconds=30)
    coord.update_interval = timedelta(seconds=30)
    coord._ws_client = None
    return coord


def test_apply_settings_resizes_buffers_and_updates_timers() -> None:
    coord = _coordinator()
    for i in range(50):
        coord.ws_devtools.record(topic="T", device_id=None, payload=i)

    coord.apply_settings({"scan_interval": 90, "devtools_buffer_size": 20, "command_timeout": 25})

    assert coord._user_update_interval == timedelta(seconds=90)
    assert coord.update_interval == timedelta(seconds=90), (
        "WS is down — the user interval applies now"
    )
    assert coord.ws_devtools.log.maxlen == 20
    assert [r["payload"] for r in coord.ws_devtools.log][0] == 30, "newest entries are kept"
    assert coord._ws_log is coord.ws_devtools.log, "the log WS endpoint reads the alias"
    assert coord.diff_collector.maxlen == 20
    assert coord.command_tracker.maxlen == 20
    assert coord.command_tracker.command_timeout == 25


def test_apply_settings_keeps_the_ws_interval_while_ws_is_up() -> None:
    coord = _coordinator()
    coord._ws_client = MagicMock(is_connected=True)
    coord.update_interval = timedelta(seconds=600)
    coord.apply_settings({"scan_interval": 90})
    assert coord._user_update_interval == timedelta(seconds=90)
    assert coord.update_interval == timedelta(seconds=600)


@pytest.mark.asyncio
async def test_listener_applies_live_settings_without_reload() -> None:
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = MagicMock(entry_id="e1", options={"scan_interval": 60, "enabled_device_uids": ["a"]})
    entry.runtime_data = MagicMock()
    hass.data = {f"{DOMAIN}_options_e1": {"scan_interval": 30, "enabled_device_uids": ["a"]}}

    await _async_entry_updated(hass, entry)

    hass.config_entries.async_reload.assert_not_called()
    entry.runtime_data.apply_settings.assert_called_once_with(entry.options)
    assert hass.data[f"{DOMAIN}_options_e1"] == entry.options


@pytest.mark.asyncio
async def test_listener_still_reloads_on_selection_change() -> None:
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = MagicMock(entry_id="e1", options={"enabled_device_uids": ["a", "b"]})
    hass.data = {f"{DOMAIN}_options_e1": {"enabled_device_uids": ["a"]}}

    await _async_entry_updated(hass, entry)

    hass.config_entries.async_reload.assert_awaited_once_with("e1")


@pytest.mark.asyncio
async def test_listener_does_not_reload_entry_without_options_snapshot() -> None:
    """Снимка нет, пока запись выгружается или перезагружается (unload его
    удаляет). Смена options в этот момент не должна запускать ещё один reload:
    новая настройка и так прочитает актуальные options."""
    hass = MagicMock()
    hass.config_entries.async_reload = AsyncMock()
    entry = MagicMock(entry_id="e1", options={"enabled_device_uids": ["a", "b"]})
    hass.data = {}

    await _async_entry_updated(hass, entry)

    hass.config_entries.async_reload.assert_not_called()
    entry.runtime_data.apply_settings.assert_not_called()
    assert hass.data == {}


@pytest.mark.asyncio
async def test_options_flow_offers_every_live_setting() -> None:
    from unittest.mock import PropertyMock

    from custom_components.sberhome.config_flow import SberHomeOptionsFlow
    from custom_components.sberhome.settings import SETTINGS_DEFAULTS

    flow = SberHomeOptionsFlow()
    type(flow).config_entry = PropertyMock(return_value=MagicMock(options={}))
    shown: dict = {}
    flow.async_show_form = lambda **kw: shown.update(kw) or kw
    flow.add_suggested_values_to_schema = lambda schema, _values: schema
    try:
        await flow.async_step_init(user_input=None)
    finally:
        del type(flow).config_entry
    assert {str(k) for k in shown["data_schema"].schema} == set(SETTINGS_DEFAULTS)
