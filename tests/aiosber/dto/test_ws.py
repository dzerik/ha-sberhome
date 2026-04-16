"""Тесты SocketMessageDto и Topic-диспетчеризации."""

from __future__ import annotations

import pytest

from custom_components.sberhome.aiosber.dto import SocketMessageDto, Topic


def test_device_state_message_topic():
    src = {
        "state": {
            "reported_state": [{"key": "on_off", "type": "BOOL", "bool_value": True}],
            "timestamp": "2026-04-15T12:00:00.000Z",
        }
    }
    msg = SocketMessageDto.from_dict(src)
    assert msg.topic is Topic.DEVICE_STATE
    assert msg.state is not None
    assert msg.state.reported_state[0].bool_value is True


def test_devman_event_topic():
    src = {"event": {"device_id": "x", "event_type": "button_1_event"}}
    msg = SocketMessageDto.from_dict(src)
    assert msg.topic is Topic.DEVMAN_EVENT
    assert msg.event == src["event"]


def test_group_state_topic():
    msg = SocketMessageDto.from_dict({"group_state": {"id": "g1"}})
    assert msg.topic is Topic.GROUP_STATE


def test_inventory_ota_topic():
    msg = SocketMessageDto.from_dict({"fw_task_status": {"status": "downloading"}})
    assert msg.topic is Topic.INVENTORY_OTA


def test_scenario_widgets_topic():
    msg = SocketMessageDto.from_dict({"scenario_widget": {"id": "s1"}})
    assert msg.topic is Topic.SCENARIO_WIDGETS


def test_scenario_home_change_variable_topic():
    msg = SocketMessageDto.from_dict({"scenario_home_change_variable": {"at_home": True}})
    assert msg.topic is Topic.SCENARIO_HOME_CHANGE_VARIABLE


def test_launcher_widgets_topic():
    msg = SocketMessageDto.from_dict({"home_widget": {"id": "w1"}})
    assert msg.topic is Topic.LAUNCHER_WIDGETS


def test_home_transfer_topic():
    msg = SocketMessageDto.from_dict({"home_transfer": {"to_user_id": "u1"}})
    assert msg.topic is Topic.HOME_TRANSFER


def test_empty_message_has_no_topic():
    msg = SocketMessageDto.from_dict({})
    assert msg.topic is None


@pytest.mark.parametrize(
    "field,topic",
    [
        ("state", Topic.DEVICE_STATE),
        ("fw_task_status", Topic.INVENTORY_OTA),
        ("scenario_widget", Topic.SCENARIO_WIDGETS),
        ("scenario_home_change_variable", Topic.SCENARIO_HOME_CHANGE_VARIABLE),
        ("home_widget", Topic.LAUNCHER_WIDGETS),
        ("event", Topic.DEVMAN_EVENT),
        ("group_state", Topic.GROUP_STATE),
        ("home_transfer", Topic.HOME_TRANSFER),
    ],
)
def test_all_topics_dispatched(field, topic):
    """Каждое из 8 полей корректно мапится в Topic."""
    src = {field: {} if field != "state" else {"reported_state": [], "timestamp": "t"}}
    msg = SocketMessageDto.from_dict(src)
    assert msg.topic is topic
