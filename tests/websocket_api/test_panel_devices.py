"""Команды панели об устройствах: список, карточка, схема записи, перечитка."""

from __future__ import annotations

import httpx
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from ..fake_cloud import FakeSberCloud, device
from .conftest import Panel

ENABLED = {"enabled_device_uids": ["SN-lamp"]}


async def test_write_schema_describes_only_writable_attributes(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    """Форма действия строится по командам устройства с текущими значениями."""
    fake_cloud.devices = [
        device(
            "lamp",
            commands=[
                {"key": k}
                for k in (
                    "on_off",
                    "light_brightness",
                    "light_mode",
                    "light_colour",
                    "temp",
                    "label",
                )
            ],
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "light_brightness", "type": "INTEGER", "integer_value": "250"},
                {"key": "light_mode", "type": "ENUM", "enum_value": "white"},
                {"key": "light_colour", "type": "COLOR", "color_value": {"h": 1, "s": 2, "v": 3}},
                {"key": "temp", "type": "FLOAT", "float_value": 21.5},
                {"key": "label", "type": "STRING", "string_value": "x"},
                {"key": "broken", "type": "INTEGER", "integer_value": "n/a"},
            ],
            attributes=[
                {"key": "on_off", "type": "BOOL"},
                {
                    "key": "light_brightness",
                    "type": "INTEGER",
                    "int_values": {"range": {"min": 50, "max": 1000}, "unit": "%"},
                },
                {
                    "key": "light_mode",
                    "type": "ENUM",
                    "enum_values": {"values": ["white", "colour"]},
                },
                {
                    "key": "light_colour",
                    "type": "COLOR",
                    "color_values": {
                        "h": {"min": 0, "max": 360},
                        "s": {"min": 0, "max": 100, "step": 5},
                    },
                },
                {"key": "temp", "type": "FLOAT", "float_values": {"range": {"min": 5, "max": 30}}},
                {"key": "label", "type": "STRING", "color_values": {}},
                {"key": "broken", "type": "INTEGER"},
                {"key": "online", "type": "BOOL"},
            ],
        )
    ]
    await setup_sberhome(options=ENABLED)

    response = await panel("device_write_schema", device_id="lamp")

    assert response["success"]
    fields = {f["key"]: f for f in response["result"]["fields"]}
    # Атрибуты без команды (online, broken) в форму не попадают.
    assert list(fields) == [
        "on_off",
        "light_brightness",
        "light_mode",
        "light_colour",
        "temp",
        "label",
    ]
    assert fields["on_off"]["current"] is True
    assert fields["light_brightness"] == {
        "key": "light_brightness",
        "label": fields["light_brightness"]["label"],
        "type": "INTEGER",
        "current": 250,
        "range": {"min": 50, "max": 1000},
        "unit": "%",
    }
    assert fields["light_mode"]["enum"] == ["white", "colour"]
    assert fields["light_mode"]["current"] == "white"
    assert fields["light_colour"]["color"] == {
        "h": {"min": 0, "max": 360, "step": 1},
        "s": {"min": 0, "max": 100, "step": 5},
    }
    assert fields["light_colour"]["current"] == {"h": 1, "s": 2, "v": 3}
    assert fields["temp"]["frange"] == {"min": 5, "max": 30}
    assert fields["temp"]["current"] == 21.5
    assert fields["label"]["current"] == "x"
    assert "color" not in fields["label"]


async def test_write_schema_unparseable_integer_has_no_current_value(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    fake_cloud.devices = [
        device(
            "lamp",
            commands=[{"key": "light_brightness"}],
            reported=[{"key": "light_brightness", "type": "INTEGER", "integer_value": "n/a"}],
            attributes=[{"key": "light_brightness", "type": "INTEGER"}],
        )
    ]
    await setup_sberhome(options=ENABLED)

    response = await panel("device_write_schema", device_id="lamp")

    assert response["result"]["fields"][0]["current"] is None


async def test_write_schema_unknown_device_is_empty(
    hass: HomeAssistant, setup_sberhome, panel: Panel
) -> None:
    await setup_sberhome(options=ENABLED)

    response = await panel("device_write_schema", device_id="ghost")

    assert response["result"] == {"device_id": "ghost", "fields": []}


async def test_device_list_reports_location_groups_icon_and_selection(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    fake_cloud.groups = [
        {"id": "grp-1", "name": "Вытяжки", "group_type": "GROUP"},
        {"id": "grp-2", "group_type": "GROUP"},
    ]
    fake_cloud.devices = [
        device(
            "lamp",
            name="Люстра",
            group_ids=["room-1", "grp-1", "grp-2"],
            images={"cards_3d_on": "/cards/lamp.png"},
            connection_type="ConnTypeZigbee",
            reported=[{"key": "on_off", "type": "BOOL", "bool_value": True}],
        ),
        device("socket", image_set_type="dt_socket_sber", images={"list_on": "/list/socket.png"}),
        device("mystery", image_set_type="totally_unknown_thing"),
    ]
    await setup_sberhome(options=ENABLED)

    response = await panel("get_devices")

    assert response["success"]
    result = response["result"]
    assert result["configured"] is True
    by_id = {d["device_id"]: d for d in result["devices"]}
    lamp = by_id["lamp"]
    assert lamp["name"] == "Люстра"
    assert lamp["enabled"] is True
    assert lamp["platforms"] == ["light"]
    assert lamp["room_name"] == "Кухня"
    assert lamp["home_name"] == "Дом"
    assert lamp["groups"] == [{"id": "grp-1", "name": "Вытяжки"}, {"id": "grp-2", "name": "grp-2"}]
    assert lamp["icon_path"] == "/cards/lamp.png"
    assert lamp["features"] == ["on_off"]
    assert lamp["connection_type"] == "ConnTypeZigbee"
    assert lamp["ha_area_id"] is not None
    assert by_id["socket"]["enabled"] is False
    assert by_id["socket"]["icon_path"] == "/list/socket.png"
    assert by_id["socket"]["ha_area_id"] is None
    assert by_id["mystery"]["category"] is None


async def test_device_list_marks_devices_bridged_back_from_this_home_assistant(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    """Устройство, которое мост HA→Сбер выставил из этого же HA, помечено петлёй."""
    er.async_get(hass).async_get_or_create("light", "hue", "kitchen", suggested_object_id="kitchen")
    fake_cloud.devices = [
        device("light.kitchen", manufacturer="HA-SberBridge"),
        device("light.elsewhere", manufacturer="HA-SberBridge"),
        device("bridged-no-entity-id", manufacturer="HA-SberBridge"),
    ]
    await setup_sberhome(options={})

    response = await panel("get_devices")

    result = response["result"]
    assert result["configured"] is False
    by_id = {d["device_id"]: d for d in result["devices"]}
    assert by_id["light.kitchen"]["is_bridge"] is True
    assert by_id["light.kitchen"]["bridge_name"] == "HA-SberBridge"
    assert by_id["light.kitchen"]["is_own_loop"] is True
    assert by_id["light.elsewhere"]["is_own_loop"] is False
    assert by_id["bridged-no-entity-id"]["is_own_loop"] is False
    assert all(d["enabled"] for d in result["devices"])


async def test_device_detail_returns_state_entities_and_raw_payload(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    fake_cloud.devices = [
        device(
            "vac",
            image_set_type="hvac_vacuum_cleaner",
            reported=[{"key": "vacuum_cleaner_status", "type": "ENUM", "enum_value": "cleaning"}],
        )
    ]
    await setup_sberhome(options={"enabled_device_uids": ["SN-vac"]})

    response = await panel("device_detail", device_id="vac")

    assert response["success"]
    result = response["result"]
    assert result["category"] == "vacuum_cleaner"
    assert result["room_name"] == "Кухня"
    assert result["reported_state"][0]["enum_value"] == "cleaning"
    assert result["raw_payload"]["id"] == "vac"
    assert result["ha_entities"]
    # Состояние-перечисление HA сериализуется строкой, а не падает на JSON.
    assert all(
        e["state"] is None or isinstance(e["state"], (str, int, float, bool))
        for e in result["ha_entities"]
    )


async def test_device_detail_unknown_device(
    hass: HomeAssistant, setup_sberhome, panel: Panel
) -> None:
    await setup_sberhome(options={})

    response = await panel("device_detail", device_id="ghost")

    assert response["success"] is False
    assert response["error"]["code"] == "not_found"


async def test_refetch_device_returns_fresh_cloud_payload(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    fake_cloud.devices = [device("lamp")]
    await setup_sberhome(options=ENABLED)
    fake_cloud.on("GET", "/devices/lamp", {"result": {"id": "lamp", "fresh": True}})

    response = await panel("refetch_device", device_id="lamp")

    assert response["result"] == {"device_id": "lamp", "raw_payload": {"id": "lamp", "fresh": True}}


async def test_refetch_device_reports_cloud_error(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    fake_cloud.devices = [device("lamp")]
    await setup_sberhome(options=ENABLED)
    fake_cloud.on("GET", "/devices/lamp", httpx.Response(500, json={"message": "boom"}))

    response = await panel("refetch_device", device_id="lamp")

    assert response["success"] is False
    assert response["error"]["code"] == "fetch_failed"
