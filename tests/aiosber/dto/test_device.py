"""Тесты DeviceDto, DeviceInfoDto, ImagesDto, BridgeMeta."""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto import (
    AttributeValueType,
    BridgeMeta,
    ConnectionType,
    DeviceDto,
    DeviceInfoDto,
    VendorType,
)

# Реалистичный payload (минимально полный) — лампочка в группе
SAMPLE_BULB = {
    "id": "11111111-1111-1111-1111-111111111111",
    "name": "Люстра",
    "device_type_name": "bulb_sber",
    "parent_id": "22222222-2222-2222-2222-222222222222",
    "serial_number": "SBDV-W007",
    "group_ids": ["22222222-2222-2222-2222-222222222222"],
    "device_info": {
        "product_id": "SBER_BULB_W007",
        "model": "SBDV-00007",
        "matter_node_id": 0,
        "sub_device_count": 0,
    },
    "image_set_type": "bulb_sber",
    "images": {
        "list_on": "https://img.iot.sberdevices.ru/bulb_on.png",
        "list_off": "https://img.iot.sberdevices.ru/bulb_off.png",
        "photo": "https://img.iot.sberdevices.ru/bulb_photo.png",
    },
    "full_categories": ["light", "on_off", "light_brightness", "light_colour"],
    "sw_version": "1.0.5",
    "sort_weight_int": 100,
    "reported_state": [
        {"key": "online", "type": "BOOL", "bool_value": True},
        {"key": "on_off", "type": "BOOL", "bool_value": True},
        {"key": "light_brightness", "type": "INTEGER", "integer_value": 750},
        {
            "key": "light_colour",
            "type": "COLOR",
            "color_value": {"hue": 60, "saturation": 100, "brightness": 90},
        },
    ],
    "desired_state": [],
    "connection_type": "ConnTypeWireless",
    "ip": "192.168.1.42",
    "mac": "AA:BB:CC:DD:EE:FF",
    "unknown_extra_field": "harmless",  # должно игнорироваться
}


def test_device_dto_parses_full_payload():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert d.id == "11111111-1111-1111-1111-111111111111"
    assert d.name == "Люстра"
    assert d.device_type_name == "bulb_sber"
    assert d.image_set_type == "bulb_sber"
    assert d.connection_type is ConnectionType.WIRELESS
    assert d.sw_version == "1.0.5"


def test_device_info_dto_nested():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert d.device_info == DeviceInfoDto(
        product_id="SBER_BULB_W007",
        model="SBDV-00007",
        matter_node_id=0,
        sub_device_count=0,
    )


def test_images_dto_nested():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert d.images is not None
    assert d.images.list_on == "https://img.iot.sberdevices.ru/bulb_on.png"
    assert d.images.cards_3d_on is None  # отсутствовало в payload


def test_device_full_categories():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert d.full_categories == ["light", "on_off", "light_brightness", "light_colour"]


def test_device_reported_state_parsed_as_attributes():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert len(d.reported_state) == 4
    on_off = d.reported("on_off")
    assert on_off is not None
    assert on_off.type is AttributeValueType.BOOL
    assert on_off.bool_value is True


def test_device_reported_value_helper():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert d.reported_value("on_off") is True
    assert d.reported_value("light_brightness") == 750
    assert d.reported_value("doesnt_exist") is None


def test_device_color_value_parsed_correctly():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    color = d.reported("light_colour")
    assert color is not None
    assert color.color_value is not None
    assert color.color_value.hue == 60
    assert color.color_value.saturation == 100
    assert color.color_value.brightness == 90


def test_device_unknown_fields_ignored():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert d.id is not None  # парсинг не упал на unknown_extra_field


def test_device_vendor_inferred_from_type_name():
    d = DeviceDto.from_dict(SAMPLE_BULB)
    assert d.vendor is VendorType.SBER  # "bulb_sber" содержит "sber"


def test_device_to_dict_omits_none():
    d = DeviceDto.from_dict({"id": "abc", "name": "Test"})
    out = d.to_dict()
    assert "ip" not in out
    assert "mac" not in out
    assert "device_info" not in out
    assert out["id"] == "abc"
    assert out["name"] == "Test"


def test_bridge_meta_parses():
    src = {"code": 0, "message": "ok", "matter_node_id": 12345}
    bm = BridgeMeta.from_dict(src)
    assert bm.code == 0
    assert bm.message == "ok"
    assert bm.matter_node_id == 12345


def test_device_with_bridge_meta():
    payload = {
        "id": "x",
        "device_type_name": "sensor_motion",
        "connection_type": "ConnTypeZigbee",
        "bridge_meta": {"code": 1, "message": "via SberHub", "matter_node_id": 0},
    }
    d = DeviceDto.from_dict(payload)
    assert d.connection_type is ConnectionType.ZIGBEE
    assert d.bridge_meta is not None
    assert d.bridge_meta.message == "via SberHub"


def test_empty_device_dict_creates_empty_dto():
    """Граничный случай: пустой payload не должен падать."""
    d = DeviceDto.from_dict({})
    assert d is not None
    assert d.id is None
    assert d.reported_state == []
    assert d.desired_state == []
