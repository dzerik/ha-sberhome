"""Tests for sbermap.transform.dto_bridge — DeviceDto ↔ sbermap converters."""

from __future__ import annotations

from homeassistant.const import Platform

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.dto.values import (
    AttributeValueDto,
    AttributeValueType,
    ColorValue,
)
from custom_components.sberhome.sbermap import (
    HsvColor,
    ValueType,
    device_dto_to_entities,
    device_dto_to_state_bundle,
)


def _light_dto() -> DeviceDto:
    return DeviceDto(
        id="lamp-1",
        name="Hallway Lamp",
        image_set_type="bulb_sber",
        desired_state=[
            AttributeValueDto(
                key="on_off", type=AttributeValueType.BOOL, bool_value=True
            ),
            AttributeValueDto(
                key="light_brightness",
                type=AttributeValueType.INTEGER,
                integer_value=500,
            ),
            AttributeValueDto(
                key="light_colour",
                type=AttributeValueType.COLOR,
                color_value=ColorValue(hue=120, saturation=80, brightness=70),
            ),
            AttributeValueDto(
                key="light_mode",
                type=AttributeValueType.ENUM,
                enum_value="colour",
            ),
        ],
        reported_state=[
            AttributeValueDto(
                key="on_off", type=AttributeValueType.BOOL, bool_value=False
            ),
        ],
    )


class TestStateBundleConversion:
    def test_color_value_converts_to_hsv(self):
        bundle = device_dto_to_state_bundle(_light_dto())
        color = bundle.get("light_colour")
        assert color is not None
        assert color.type is ValueType.COLOR
        assert isinstance(color.color_value, HsvColor)
        assert color.color_value.hue == 120
        assert color.color_value.saturation == 80
        assert color.color_value.brightness == 70

    def test_desired_state_overrides_reported(self):
        bundle = device_dto_to_state_bundle(_light_dto())
        # desired on_off=True должен победить reported on_off=False.
        assert bundle.value_of("on_off") is True

    def test_integer_and_enum_values(self):
        bundle = device_dto_to_state_bundle(_light_dto())
        assert bundle.value_of("light_brightness") == 500
        assert bundle.value_of("light_mode") == "colour"

    def test_device_id_propagated(self):
        bundle = device_dto_to_state_bundle(_light_dto())
        assert bundle.device_id == "lamp-1"

    def test_empty_dto_yields_empty_bundle(self):
        dto = DeviceDto(id="x")
        bundle = device_dto_to_state_bundle(dto)
        assert bundle.states == ()
        assert bundle.device_id == "x"


class TestEntitiesConversion:
    def test_light_dto_yields_light_entity(self):
        ents = device_dto_to_entities(_light_dto())
        primary = next(e for e in ents if e.platform is Platform.LIGHT)
        assert primary.unique_id == "lamp-1"
        assert primary.name == "Hallway Lamp"
        assert primary.state == "on"

    def test_unknown_image_yields_empty_list(self):
        dto = DeviceDto(
            id="unknown-device",
            name="Mysterious",
            image_set_type="completely_alien_xyz_999",
        )
        assert device_dto_to_entities(dto) == []

    def test_socket_yields_switch_plus_sensors(self):
        dto = DeviceDto(
            id="plug-1",
            name="Smart Plug",
            image_set_type="dt_socket_sber",
            desired_state=[
                AttributeValueDto(
                    key="on_off", type=AttributeValueType.BOOL, bool_value=True
                ),
            ],
            reported_state=[
                AttributeValueDto(
                    key="cur_voltage",
                    type=AttributeValueType.FLOAT,
                    float_value=222.5,
                ),
                AttributeValueDto(
                    key="cur_current",
                    type=AttributeValueType.INTEGER,
                    integer_value=150,
                ),
                AttributeValueDto(
                    key="cur_power",
                    type=AttributeValueType.FLOAT,
                    float_value=33.4,
                ),
            ],
        )
        ents = device_dto_to_entities(dto)
        platforms = {e.platform for e in ents}
        assert Platform.SWITCH in platforms
        assert Platform.SENSOR in platforms
        sensor_keys = {e.unique_id for e in ents if e.platform is Platform.SENSOR}
        assert {"plug-1_voltage", "plug-1_current", "plug-1_power"} <= sensor_keys

    def test_dto_without_id_falls_back_to_empty(self):
        dto = DeviceDto(image_set_type="bulb_sber", name="Anon")
        ents = device_dto_to_entities(dto)
        # Бракованный DTO без id всё равно не должен крашнуть.
        assert all(e.unique_id == "" for e in ents)
