"""Тесты body-DTO для PUT/POST запросов."""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto import (
    ChangeDeviceOrderElementsBody,
    CreateDeviceLinkBody,
    DeviceOrderElement,
    DeviceToPairingBody,
    ElementType,
    IndicatorColor,
    IndicatorColorBody,
    UpdateNameBody,
    UpdateParentBody,
)


def test_update_name_body():
    body = UpdateNameBody(name="Кухня")
    assert body.to_dict() == {"name": "Кухня"}


def test_update_parent_body_with_group():
    body = UpdateParentBody(parent_id="grp-uuid")
    assert body.to_dict() == {"parent_id": "grp-uuid"}


def test_update_parent_body_without_group_keeps_field():
    """parent_id=None означает «вынести из группы», поле должно остаться."""
    body = UpdateParentBody()
    assert body.to_dict() == {"parent_id": None}


def test_create_device_link_body():
    body = CreateDeviceLinkBody(type="TEMPERATURE_CORRECTION", from_device_id="a", to_device_id="b")
    assert body.to_dict() == {
        "type": "TEMPERATURE_CORRECTION",
        "from_device_id": "a",
        "to_device_id": "b",
    }


def test_change_device_order():
    body = ChangeDeviceOrderElementsBody(
        elements=[
            DeviceOrderElement(id="1", type=ElementType.DEVICE),
            DeviceOrderElement(id="g1", type=ElementType.GROUP),
        ]
    )
    out = body.to_dict()
    assert out["elements"] == [
        {"id": "1", "type": "DEVICE"},
        {"id": "g1", "type": "GROUP"},
    ]


def test_indicator_color_body():
    body = IndicatorColorBody(
        indicator_color=IndicatorColor(id="led-1", hue=120, saturation=80, brightness=90)
    )
    assert body.to_dict() == {
        "indicator_color": {
            "id": "led-1",
            "hue": 120,
            "saturation": 80,
            "brightness": 90,
        }
    }


def test_device_to_pairing_body_minimal():
    body = DeviceToPairingBody(image_set_type="bulb_sber", pairing_type="wifi")
    out = body.to_dict()
    assert out == {"image_set_type": "bulb_sber", "pairing_type": "wifi"}


def test_device_to_pairing_body_with_extras():
    body = DeviceToPairingBody(
        device_id="x",
        timeout=120,
        extra={"ssid": "MyWiFi", "password": "secret"},
    )
    out = body.to_dict()
    assert out["device_id"] == "x"
    assert out["timeout"] == 120
    assert out["extra"]["ssid"] == "MyWiFi"
