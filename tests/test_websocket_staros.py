"""Tests for the sberhome/staros/list WebSocket command.

Guards the payload shape the panel «Колонки» tab reads directly (devices,
settings grouped by serial, entity_id resolution).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from homeassistant.const import STATE_ON, Platform

from custom_components.sberhome.sbermap import StarosSettingEntity
from custom_components.sberhome.websocket_api.staros import ws_staros_list


def _band_spec() -> StarosSettingEntity:
    return StarosSettingEntity(
        platform=Platform.NUMBER,
        unique_id="staros_SN1_equalizer_band_0",
        name="Эквалайзер 60 Гц",
        node_id="equalizer__band_0",
        node_type="EQUALIZER",
        product="sberboom",
        serial="SN1",
        state=1.5,
        eq_group="equalizer",
        eq_role="band",
        eq_band_index=0,
        eq_frequency=60,
    )


def _switch_spec() -> StarosSettingEntity:
    return StarosSettingEntity(
        platform=Platform.SWITCH,
        unique_id="staros_SN1_child",
        name="Детский режим",
        node_id="child",
        node_type="TOGGLE",
        product="sberboom",
        serial="SN1",
        state=STATE_ON,
    )


def _coordinator() -> MagicMock:
    coord = MagicMock()
    dev = MagicMock()
    dev.serial_number = "SN1"
    dev.product = "sberboom-r2"
    dev.name = "Кухня"
    coord.staros_devices = [dev]
    coord.staros_settings_entities = {"SN1": [_band_spec(), _switch_spec()]}
    coord.has_staros_settings.return_value = True
    coord.staros_speaker_present.return_value = True
    return coord


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


def test_staros_list_returns_devices_and_settings(connection):
    coord = _coordinator()
    reg = MagicMock()
    reg.async_get_entity_id.side_effect = lambda platform, domain, uid: f"{platform}.{uid}"
    with (
        patch(
            "custom_components.sberhome.websocket_api.staros.get_coordinator",
            return_value=coord,
        ),
        patch(
            "custom_components.sberhome.websocket_api.staros.er.async_get",
            return_value=reg,
        ),
    ):
        ws_staros_list(MagicMock(), connection, {"id": 7})

    payload = connection.send_result.call_args[0][1]
    assert payload["available"] is True
    assert payload["speaker_present"] is True
    assert payload["devices"] == [{"serial": "SN1", "product": "sberboom-r2", "name": "Кухня"}]
    specs = payload["settings"]["SN1"]
    band = next(s for s in specs if s["eq_role"] == "band")
    assert band["eq_frequency"] == 60
    assert band["entity_id"] == "number.staros_SN1_equalizer_band_0"
    toggle = next(s for s in specs if s["node_id"] == "child")
    assert toggle["platform"] == "switch"
    assert toggle["entity_id"] == "switch.staros_SN1_child"


def test_staros_list_not_loaded(connection):
    with patch(
        "custom_components.sberhome.websocket_api.staros.get_coordinator",
        return_value=None,
    ):
        ws_staros_list(MagicMock(), connection, {"id": 8})
    connection.send_error.assert_called_once()
    assert connection.send_result.call_count == 0
