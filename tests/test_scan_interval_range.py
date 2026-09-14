"""Один допустимый диапазон интервала опроса во всех формах настройки.

Форма параметров интеграции принимала 10–300 секунд, а панель и её
WS-команда — 10–3600. Значение, сохранённое из панели (например, 900),
форма параметров потом отказывалась принять обратно.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock

import pytest
import voluptuous as vol

from custom_components.sberhome.config_flow import SberHomeOptionsFlow
from custom_components.sberhome.const import (
    CONF_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from custom_components.sberhome.websocket_api.settings import ws_update_settings


async def _options_schema() -> vol.Schema:
    flow = SberHomeOptionsFlow()
    entry = MagicMock()
    entry.options = {CONF_SCAN_INTERVAL: 60}
    type(flow).config_entry = PropertyMock(return_value=entry)
    shown: dict = {}
    flow.async_show_form = lambda **kwargs: shown.update(kwargs) or kwargs
    flow.add_suggested_values_to_schema = lambda schema, _values: schema
    try:
        await flow.async_step_init(user_input=None)
    finally:
        del type(flow).config_entry
    return shown["data_schema"]


def _ws_schema() -> vol.Schema:
    return vol.Schema(ws_update_settings._ws_schema, extra=vol.ALLOW_EXTRA)


@pytest.mark.parametrize("value", [MIN_SCAN_INTERVAL, 900, MAX_SCAN_INTERVAL])
async def test_both_forms_accept_the_same_values(value: int) -> None:
    (await _options_schema())({CONF_SCAN_INTERVAL: value})
    _ws_schema()({"type": "sberhome/update_settings", "id": 1, "scan_interval": value})


@pytest.mark.parametrize("value", [MIN_SCAN_INTERVAL - 1, MAX_SCAN_INTERVAL + 1])
async def test_both_forms_reject_the_same_values(value: int) -> None:
    with pytest.raises(vol.Invalid):
        (await _options_schema())({CONF_SCAN_INTERVAL: value})
    with pytest.raises(vol.Invalid):
        _ws_schema()({"type": "sberhome/update_settings", "id": 1, "scan_interval": value})
