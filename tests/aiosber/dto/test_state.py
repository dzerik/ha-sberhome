"""Тесты DesiredDeviceStateDto, DesiredGroupStateDto, StateDto."""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto import (
    AttributeValueDto,
    AttributeValueType,
    AttrKey,
    ColorValue,
    DesiredDeviceStateDto,
    DesiredGroupStateDto,
    DeviceOrderElement,
    ElementType,
    StateDto,
)


# ============== DesiredDeviceStateDto (PUT devices/{id}/state) ==============
def test_desired_device_state_command_serialization():
    """Команда лампе: включить + поставить яркость + цвет."""
    body = DesiredDeviceStateDto(
        desired_state=[
            AttributeValueDto.of_bool(AttrKey.ON_OFF, True),
            AttributeValueDto.of_int(AttrKey.LIGHT_BRIGHTNESS, 600),
            AttributeValueDto.of_color(
                AttrKey.LIGHT_COLOUR, ColorValue(hue=180, saturation=80, brightness=70)
            ),
        ]
    )
    expected = {
        "desired_state": [
            {"key": "on_off", "type": "BOOL", "bool_value": True},
            {"key": "light_brightness", "type": "INTEGER", "integer_value": 600},
            {
                "key": "light_colour",
                "type": "COLOR",
                "color_value": {"hue": 180, "saturation": 80, "brightness": 70},
            },
        ],
    }
    assert body.to_dict() == expected


def test_desired_device_state_keeps_empty_list_field():
    """Даже пустой desired_state должен сериализоваться (omit_none=False)."""
    body = DesiredDeviceStateDto()
    assert body.to_dict() == {"desired_state": []}


def test_desired_device_state_roundtrip():
    src = {
        "desired_state": [
            {"key": "on_off", "type": "BOOL", "bool_value": False},
        ]
    }
    body = DesiredDeviceStateDto.from_dict(src)
    assert len(body.desired_state) == 1
    assert body.desired_state[0].bool_value is False
    assert body.to_dict() == src


# ============== DesiredGroupStateDto ==============
def test_desired_group_state_with_return_status():
    body = DesiredGroupStateDto(
        desired_state=[AttributeValueDto.of_bool("on_off", True)],
        return_group_status=True,
    )
    out = body.to_dict()
    assert out["return_group_status"] is True
    assert out["desired_state"][0]["bool_value"] is True


def test_desired_group_state_without_return_status_omits_field():
    body = DesiredGroupStateDto(
        desired_state=[AttributeValueDto.of_bool("on_off", True)]
    )
    assert "return_group_status" not in body.to_dict()


# ============== StateDto (WS DEVICE_STATE) ==============
def test_state_dto_parses_ws_message():
    src = {
        "device_id": "abc-123",
        "reported_state": [
            {"key": "on_off", "type": "BOOL", "bool_value": True},
            {"key": "light_brightness", "type": "INTEGER", "integer_value": 500},
        ],
        "timestamp": "2026-04-15T12:34:56.789Z",
    }
    s = StateDto.from_dict(src)
    assert s.device_id == "abc-123"
    assert s.timestamp == "2026-04-15T12:34:56.789Z"
    assert len(s.reported_state) == 2
    assert s.reported_state[0].type is AttributeValueType.BOOL
    assert s.reported_state[1].integer_value == 500


def test_state_dto_without_device_id():
    """device_id optional — backward compat."""
    src = {
        "reported_state": [
            {"key": "on_off", "type": "BOOL", "bool_value": True},
        ],
        "timestamp": "t",
    }
    s = StateDto.from_dict(src)
    assert s.device_id is None
    assert len(s.reported_state) == 1


# ============== DeviceOrderElement (PUT devices/order) ==============
def test_device_order_element_serialization():
    el = DeviceOrderElement(id="abc-123", type=ElementType.DEVICE)
    assert el.to_dict() == {"id": "abc-123", "type": "DEVICE"}


def test_device_order_element_group_type():
    el = DeviceOrderElement(id="grp-1", type=ElementType.GROUP)
    assert el.to_dict() == {"id": "grp-1", "type": "GROUP"}


def test_device_order_element_roundtrip():
    src = {"id": "x", "type": "DEVICE"}
    el = DeviceOrderElement.from_dict(src)
    assert el.type is ElementType.DEVICE
    assert el.to_dict() == src
