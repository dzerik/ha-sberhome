"""Контракт DTO: разбор реальных ответов Sber, round-trip и устойчивость к мусору.

Все DTO разбирают ответы, форма которых у Sber «плывёт». Тесты фиксируют
общий контракт: отсутствующий вложенный объект → ``None``, сериализация
обратима, неожиданные типы полей не роняют разбор всего устройства.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import pkgutil

import pytest

from custom_components.sberhome.aiosber import dto as dto_pkg
from custom_components.sberhome.aiosber.dto import (
    AttributeValueDto,
    AttributeValueType,
    AttrKey,
    ChangeDeviceOrderElementsBody,
    ColorValue,
    CreateDeviceLinkBody,
    DesiredGroupStateDto,
    DeviceDto,
    DeviceFeatureDto,
    DeviceOrderElement,
    DeviceToPairingBody,
    ElementType,
    IndicatorColor,
    IndicatorColorBody,
    IndicatorColors,
    NameDto,
    ScenarioDto,
    ScenarioEventDto,
    ScheduleDay,
    ScheduleValue,
    SettingNodeDto,
    SocketMessageDto,
    Topic,
    UnionTreeDto,
    UpdateNameBody,
    UpdateParentBody,
    button_event_key,
)
from custom_components.sberhome.aiosber.dto._serde import dataclass_to_dict, from_dict


def _dto_classes() -> list[type]:
    classes: dict[str, type] = {}
    for info in pkgutil.walk_packages(dto_pkg.__path__, dto_pkg.__name__ + "."):
        module = importlib.import_module(info.name)
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if (
                obj.__module__ == module.__name__
                and dataclasses.is_dataclass(obj)
                and "from_dict" in vars(obj)
            ):
                classes[f"{obj.__module__}.{obj.__qualname__}"] = obj
    return [classes[k] for k in sorted(classes)]


_DTO_CLASSES = _dto_classes()


def test_dto_discovery_finds_the_models():
    names = {cls.__name__ for cls in _DTO_CLASSES}
    assert {"DeviceDto", "DeviceFeatureDto", "SocketMessageDto", "UnionDto"} <= names


@pytest.mark.parametrize("cls", _DTO_CLASSES, ids=lambda c: c.__name__)
def test_absent_object_parses_to_none(cls):
    """`null` вместо вложенного объекта — нет объекта, а не исключение."""
    assert cls.from_dict(None) is None


# ---------------------------------------------------------------------------
# Реалистичное устройство из /device_groups/tree
# ---------------------------------------------------------------------------

THERMOSTAT = {
    "id": "a1b2c3d4-0000-4000-8000-00000000c0de",
    "name": {"name": "Тёплый пол", "defaultName": "Терморегулятор", "names": {}},
    "device_type_name": "dt_thermostat_sber",
    "parent_id": "room-bathroom",
    "routing_key": "rk-7",
    "serial_number": "SBDV-TH-0042",
    "external_id": "ext-42",
    "group_ids": ["room-bathroom", "home-1"],
    "device_info": {
        "product_id": "SBER_TH_01",
        "model": {"model": "SBDV-00115", "manufacturer": "SberDevices"},
        "matter_node_id": 0,
        "sub_device_count": 0,
    },
    "reported_state": [
        {"key": "online", "type": "BOOL", "bool_value": True},
        {"key": "hvac_temp_set", "type": "INTEGER", "integer_value": "28"},
        {"key": "temperature", "type": "FLOAT", "float_value": 26.5},
        {"key": "hvac_thermostat_mode", "type": "ENUM", "enum_value": "comfort"},
        {
            "key": "schedule",
            "type": "SCHEDULE",
            "schedule_value": {
                "days": ["monday", "friday"],
                "events": [{"time": "07:30", "value_type": "INTEGER", "target_value": 30}],
            },
        },
    ],
    "desired_state": [],
    "correction": {"formula_type": "LINEAR", "data": {"k": 1, "b": -0.5}},
    "image_set_type": "dt_thermostat_sber",
    "images": {"list_on": "https://img.iot.sberdevices.ru/th_on.png"},
    "attributes": [
        {
            "key": "hvac_temp_set",
            "type": "INTEGER",
            "name": "Целевая температура",
            "is_visible": True,
            "int_values": {"range": {"min": 5, "max": 35, "step": 1}, "unit": "celsius"},
        },
        {
            "key": "temperature",
            "type": "FLOAT",
            "float_values": {"range": {"min": -10.0, "max": 60.0}, "unit": "celsius"},
        },
        {"key": "name_label", "type": "STRING", "string_values": {"maxLength": 32}},
        {
            "key": "hvac_thermostat_mode",
            "type": "ENUM",
            "enum_values": {"values": ["comfort", "eco", "anti_frost"]},
        },
        {
            "key": "light_colour",
            "type": "COLOR",
            "color_values": {
                "h": {"min": 0, "max": 360, "step": 1},
                "s": {"min": 0, "max": 1000, "step": 1},
                "v": {"min": 100, "max": 1000, "step": 1},
            },
        },
        {"key": "schedule", "type": "SCHEDULE", "schedule_values": {}},
    ],
    "full_categories": [
        {
            "id": "hvac_underfloor_heating",
            "name": "Тёплый пол",
            "slug": "hvac_underfloor_heating",
            "default_name": "Тёплый пол",
            "image_set_type": "cat_underfloor_m",
            "sort_weight": 3,
        }
    ],
    "sw_version": "2.4.1",
    "coprocessor_fw_version": "1.0.9",
    "sort_weight_int": 7,
    "commands": [{"key": "reset_filter", "state_fields": ["hvac_replace_filter"]}],
    "children": {"count": 0, "limit": 32},
    "linked": [{"id": "lnk-1", "type": "TEMPERATURE_CORRECTION", "to_id": "s-1", "from_id": "t-1"}],
    "owner_info": {"is_owner": True},
    "connection_type": "ConnTypeWireless",
    "ip": "192.168.1.42",
    "mac": "AA:BB:CC:DD:EE:42",
    "bridge_meta": {"code": 0, "message": "ok", "matter_node_id": 0},
    "landing_id": "landing-th",
}


def test_full_device_payload_parses_every_nested_model():
    dev = DeviceDto.from_dict(THERMOSTAT)
    assert dev is not None
    assert dev.name.default_name == "Терморегулятор"
    assert dev.device_info.model == "SBDV-00115"
    assert dev.device_info.manufacturer == "SberDevices"
    assert dev.reported_value("hvac_temp_set") == 28
    schedule = dev.reported_value("schedule")
    assert schedule.days == [ScheduleDay.MONDAY, ScheduleDay.FRIDAY]
    assert schedule.events[0].value_type is AttributeValueType.INTEGER
    assert dev.correction.data == {"k": 1, "b": -0.5}
    by_key = {a.key: a for a in dev.attributes}
    assert by_key["hvac_temp_set"].int_values.range.max == 35
    assert by_key["temperature"].float_values.range.min == -10.0
    assert by_key["name_label"].string_values.max_length == 32
    assert by_key["light_colour"].color_values.s.max == 1000
    assert by_key["schedule"].schedule_values is not None
    assert dev.commands[0].state_fields == ["hvac_replace_filter"]
    assert dev.children.limit == 32
    assert dev.linked[0].to_id == "s-1"
    assert dev.owner_info.is_owner is True
    assert dev.bridge_meta.message == "ok"
    assert dev.primary_category_slug == "hvac_underfloor_heating"


def test_full_device_serializes_back_to_equal_model():
    dev = DeviceDto.from_dict(THERMOSTAT)
    assert DeviceDto.from_dict(dev.to_dict()) == dev


def test_device_vendor_heuristics():
    assert DeviceDto(device_type_name="dt_bulb_tuya").vendor is not None
    assert DeviceDto(device_type_name="custom_zigbee_thing").vendor is None
    assert DeviceDto().vendor is None


def test_device_name_variants():
    assert DeviceDto.from_dict({"name": "Люстра"}).display_name == "Люстра"
    assert DeviceDto().display_name is None
    # Прямое построение со строкой (legacy-моки) тоже даёт имя.
    assert DeviceDto(name="Бра").display_name == "Бра"  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WS-сообщения всех топиков
# ---------------------------------------------------------------------------

_WS_PAYLOADS = [
    (
        Topic.DEVICE_STATE,
        {
            "state": {
                "device_id": "dev-1",
                "reported_state": [{"key": "on_off", "type": "BOOL", "bool_value": True}],
                "timestamp": "2026-09-15T10:00:00.123Z",
            }
        },
    ),
    (
        Topic.INVENTORY_OTA,
        {
            "fw_task_status": {
                "id": "ota-1",
                "firmware_id": "fw-2.4.2",
                "update_status": "IN_PROGRESS",
                "percent": 40,
                "retry_count": 0,
                "version": "2.4.2",
            }
        },
    ),
    (Topic.SCENARIO_WIDGETS, {"scenario_widget": {"id": "w-1", "name": "Утро", "type": "RUN"}}),
    (
        Topic.SCENARIO_HOME_CHANGE_VARIABLE,
        {
            "scenario_home_change_variable": {
                "changeType": "UPDATE",
                "id": "var-at-home",
                "variable": {"name": "at_home", "value": {"bool_value": False}},
            }
        },
    ),
    (Topic.LAUNCHER_WIDGETS, {"home_widget": {"categories": []}}),
    (
        Topic.DEVMAN_EVENT,
        {"event": {"type": "BUTTON_CLICK", "device_id": "btn-1", "device": {"button": 1}}},
    ),
    (
        Topic.GROUP_STATE,
        {
            "group_state": {
                "type": "ROOM",
                "id": "room-kitchen",
                "status": {"online": True},
                "updatedAt": "2026-09-15T10:00:00Z",
            }
        },
    ),
    (
        Topic.HOME_TRANSFER,
        {"home_transfer": {"type": "RECEIVE", "to_user_id": "u-2", "from_user_id": "u-1"}},
    ),
]


@pytest.mark.parametrize(("topic", "payload"), _WS_PAYLOADS, ids=lambda v: str(v)[:24])
def test_ws_message_topic_and_roundtrip(topic, payload):
    msg = SocketMessageDto.from_dict(payload)
    assert msg.topic is topic
    assert SocketMessageDto.from_dict(msg.to_dict()) == msg


def test_ws_camel_case_keys_are_mapped():
    group = SocketMessageDto.from_dict(dict(_WS_PAYLOADS[6][1])).group_state
    assert group.updated_at == "2026-09-15T10:00:00Z"
    variable = SocketMessageDto.from_dict(dict(_WS_PAYLOADS[3][1])).scenario_home_change_variable
    assert variable.change_type == "UPDATE"


def test_group_tree_roundtrip():
    tree = UnionTreeDto.from_dict(
        {
            "group": {"id": "home-1", "name": "Дом", "group_type": "HOME"},
            "devices": [THERMOSTAT],
            "children": [{"group": {"id": "room-1", "group_type": "ROOM"}, "devices": []}],
        }
    )
    assert tree.children[0].union.id == "room-1"
    serialized = tree.to_dict()
    assert serialized["union"]["group_type"] == "HOME"
    assert serialized["devices"][0]["id"] == THERMOSTAT["id"]
    assert UnionTreeDto.from_dict("not-a-tree") is None  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Тела запросов
# ---------------------------------------------------------------------------

_BODIES = [
    UpdateNameBody(name="Кухня"),
    CreateDeviceLinkBody(type="TEMPERATURE_CORRECTION", from_device_id="a", to_device_id="b"),
    ChangeDeviceOrderElementsBody(
        elements=[
            DeviceOrderElement(id="dev-1", type=ElementType.DEVICE),
            DeviceOrderElement(id="room-1", type=ElementType.GROUP),
        ]
    ),
    IndicatorColorBody(indicator_color=IndicatorColor(id="led", hue=10, saturation=20)),
    DeviceToPairingBody(image_set_type="bulb_sber", pairing_type="wifi", extra={"ssid": "x"}),
    IndicatorColors(current_colors=[IndicatorColor(id="online", hue=120)]),
    UpdateParentBody(parent_id="room-1"),
    DesiredGroupStateDto(
        desired_state=[AttributeValueDto.of_bool(AttrKey.ON_OFF, False)], return_group_status=True
    ),
    ScenarioDto(
        id="sc-1",
        name="Утро",
        is_active=True,
        home_id="home-1",
        steps=[{"tasks": [{"type": "DEVICE_COMMAND", "device_id": "dev-1"}]}],
    ),
    ScenarioEventDto(
        id="69ef5a41c0372739c61340a6",
        event_time="2026-04-27T12:44:49.430277Z",
        object_id="sc-1",
        object_type="SCENARIO",
        type="SUCCESS",
        data={"scenario_cancel_time": None},
    ),
]


@pytest.mark.parametrize("body", _BODIES, ids=lambda b: type(b).__name__)
def test_request_body_roundtrip(body):
    assert type(body).from_dict(body.to_dict()) == body


# ---------------------------------------------------------------------------
# Значения атрибутов
# ---------------------------------------------------------------------------


def test_untyped_color_value_falls_back_to_color():
    color = ColorValue(hue=200, saturation=50, brightness=80)
    assert AttributeValueDto(key="light_colour", color_value=color).value == color
    assert AttributeValueDto(key="empty").value is None


def test_color_value_accepts_long_keys():
    assert ColorValue.from_dict({"hue": 10, "saturation": 20, "brightness": 30}) == ColorValue(
        10, 20, 30
    )


def test_schedule_value_roundtrip():
    value = AttributeValueDto.from_dict(THERMOSTAT["reported_state"][4])
    assert value.value == ScheduleValue.from_dict(value.schedule_value.to_dict())


# ---------------------------------------------------------------------------
# Устойчивость generic serde
# ---------------------------------------------------------------------------


def test_unknown_enum_value_becomes_none_without_losing_the_rest():
    feature = DeviceFeatureDto.from_dict({"key": "new_attr", "type": "QUANTUM", "name": "Новое"})
    assert feature.type is None
    assert feature.name == "Новое"


def test_wrong_shapes_degrade_per_field():
    dev = DeviceDto.from_dict(
        {
            "id": "dev-1",
            "device_info": ["unexpected", "list"],  # объект стал списком
            "group_ids": "room-1",  # список стал строкой
            "correction": {"formula_type": "LINEAR", "data": ["k", 1]},  # dict стал списком
            "reported_state": [
                {"key": "light_colour", "type": "COLOR", "color_value": {"h": "red"}},
            ],
        }
    )
    assert dev.id == "dev-1"
    assert dev.device_info is None
    assert dev.group_ids == []
    assert dev.correction.data == {}
    # Нечисловой компонент цвета выбрасывает только это поле.
    assert dev.reported_state[0].key == "light_colour"
    assert dev.reported_state[0].color_value is None


def test_non_dict_payload_and_non_dataclass_target():
    assert from_dict(DeviceDto, ["not", "a", "dict"]) is None  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="not a dataclass"):
        from_dict(int, {"x": 1})


@dataclasses.dataclass
class _PlainNested:
    label: str | None = None


@dataclasses.dataclass
class _Container:
    nested: _PlainNested | None = None
    mixed: int | str | None = None


def test_plain_nested_dataclass_without_own_serde():
    """Вложенный dataclass без собственных from_dict/to_dict идёт через generic serde."""
    parsed = from_dict(_Container, {"nested": {"label": "x"}, "mixed": "auto"})
    assert parsed == _Container(nested=_PlainNested(label="x"), mixed="auto")
    assert dataclass_to_dict(parsed) == {"nested": {"label": "x"}, "mixed": "auto"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Люстра", NameDto(name="Люстра")),
        (
            {"name": "Люстра", "defaultName": "Лампа", "names": {"en": "Lamp"}},
            NameDto(name="Люстра", default_name="Лампа", names={"en": "Lamp"}),
        ),
        (42, None),
    ],
    ids=["legacy-string", "camel-case", "garbage"],
)
def test_name_dto_accepts_both_wire_forms(raw, expected):
    assert NameDto.from_dict(raw) == expected


@pytest.mark.parametrize(
    ("attr", "expected"),
    [
        (AttributeValueDto(key="k", bool_value=False), False),
        (AttributeValueDto(key="k", integer_value=500), 500),
        (AttributeValueDto(key="k", float_value=21.5), 21.5),
        (AttributeValueDto(key="k", enum_value="eco"), "eco"),
        (AttributeValueDto(key="k", string_value="abc"), "abc"),
        (AttributeValueDto.of_float("temperature", 21.5), 21.5),
        (AttributeValueDto.of_string("label", "abc"), "abc"),
    ],
)
def test_attribute_value_resolves_typed_and_untyped_values(attr, expected):
    assert attr.value == expected


def test_button_event_key_bounds():
    assert button_event_key(1) == "button_1_event"
    assert button_event_key(10) == "button_10_event"
    for bad in (0, 11):
        with pytest.raises(ValueError, match="out of range"):
            button_event_key(bad)


def test_ws_target_device_id_priority():
    event = SocketMessageDto.from_dict(dict(_WS_PAYLOADS[5][1]))
    group = SocketMessageDto.from_dict(dict(_WS_PAYLOADS[6][1]))
    ota = SocketMessageDto.from_dict(dict(_WS_PAYLOADS[1][1]))
    assert event.target_device_id == "btn-1"
    assert group.target_device_id == "room-kitchen"
    assert ota.target_device_id is None


def test_setting_node_options_in_screen_list_and_bands_in_value():
    """«Светомузыка»: опции прямо в `screen`; эквалайзер: полосы в `value.user`."""
    radio = SettingNodeDto.from_dict(
        {
            "id": "lightMusic",
            "type": "RADIO_BUTTONS",
            "checked": "off",
            "screen": [{"title": "Выкл", "value": "off"}, {"title": "Вкл", "value": "on"}],
        }
    )
    assert [o.value for o in radio.options] == ["off", "on"]
    eq = SettingNodeDto.from_dict(
        {"id": "eq", "type": "EQUALIZER", "value": {"user": [1.5, -2, "x"]}}
    )
    assert eq.user_bands == [1.5, -2.0]


def test_explicit_null_nested_object_stays_none():
    assert from_dict(_Container, {"nested": None, "mixed": 7}) == _Container(mixed=7)
