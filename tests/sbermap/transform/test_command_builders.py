"""Unit tests for bidirectional command builders."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import HVACMode

from custom_components.sberhome.aiosber.dto import AttributeValueDto
from custom_components.sberhome.sbermap import (
    build_button_press_command,
    build_climate_on_off_command,
    build_climate_set_fan_mode_command,
    build_climate_set_hvac_mode_command,
    build_climate_set_temperature_command,
    build_cover_position_command,
    build_cover_stop_command,
    build_fan_preset_command,
    build_fan_turn_off_command,
    build_fan_turn_on_command,
    build_humidifier_on_off_command,
    build_humidifier_set_humidity_command,
    build_humidifier_set_mode_command,
    build_number_command,
    build_select_command,
    build_switch_command,
    build_tv_channel_command,
    build_tv_custom_key_command,
    build_tv_direction_command,
    build_tv_mute_command,
    build_tv_on_off_command,
    build_tv_source_command,
    build_tv_volume_command,
    build_tv_volume_step_command,
    build_vacuum_command,
    climate_config_for,
)


def _val(attrs: list[AttributeValueDto], key: str) -> Any:
    """Helper: find value by key in list[AttributeValueDto]."""
    for a in attrs:
        if a.key == key:
            return a.value
    return None


class TestSwitches:
    def test_primary_on_off(self):
        b = build_switch_command(device_id="d", is_on=True)
        assert _val(b, "on_off") is True

    def test_extra_switch_with_key(self):
        b = build_switch_command(device_id="d", state_key="child_lock", is_on=False)
        assert _val(b, "child_lock") is False
        assert _val(b, "on_off") is None


class TestCovers:
    def test_position(self):
        b = build_cover_position_command(device_id="d", position=42)
        assert _val(b, "open_set") == 42

    def test_stop(self):
        b = build_cover_stop_command(device_id="d")
        assert _val(b, "open_state") == "stop"


class TestClimate:
    def test_off_mode(self):
        cfg = climate_config_for("hvac_ac")
        b = build_climate_set_hvac_mode_command(
            device_id="d", hvac_mode=HVACMode.OFF, config=cfg
        )
        assert _val(b, "on_off") is False
        assert _val(b, "hvac_work_mode") is None

    def test_cool_mode(self):
        cfg = climate_config_for("hvac_ac")
        b = build_climate_set_hvac_mode_command(
            device_id="d", hvac_mode=HVACMode.COOL, config=cfg
        )
        assert _val(b, "on_off") is True
        assert _val(b, "hvac_work_mode") == "cool"

    def test_heater_no_modes_just_on(self):
        cfg = climate_config_for("hvac_heater")
        b = build_climate_set_hvac_mode_command(
            device_id="d", hvac_mode=HVACMode.HEAT, config=cfg
        )
        assert _val(b, "on_off") is True
        assert _val(b, "hvac_work_mode") is None

    def test_set_temperature(self):
        cfg = climate_config_for("hvac_ac")
        b = build_climate_set_temperature_command(
            device_id="d", temperature=22.0, config=cfg
        )
        assert _val(b, "hvac_temp_set") == 22

    def test_set_fan_mode(self):
        cfg = climate_config_for("hvac_ac")
        b = build_climate_set_fan_mode_command(
            device_id="d", fan_mode="high", config=cfg
        )
        assert _val(b, "hvac_air_flow_power") == "high"

    def test_on_off(self):
        b = build_climate_on_off_command(device_id="d", is_on=True)
        assert _val(b, "on_off") is True


class TestFan:
    def test_turn_on_with_preset(self):
        b = build_fan_turn_on_command(device_id="d", preset_mode="medium")
        assert _val(b, "on_off") is True
        assert _val(b, "hvac_air_flow_power") == "medium"

    def test_turn_on_no_preset(self):
        b = build_fan_turn_on_command(device_id="d")
        assert _val(b, "on_off") is True
        assert _val(b, "hvac_air_flow_power") is None

    def test_turn_off(self):
        b = build_fan_turn_off_command(device_id="d")
        assert _val(b, "on_off") is False

    def test_preset(self):
        b = build_fan_preset_command(device_id="d", preset_mode="high")
        assert _val(b, "hvac_air_flow_power") == "high"


class TestHumidifier:
    def test_on_off(self):
        b = build_humidifier_on_off_command(device_id="d", is_on=True)
        assert _val(b, "on_off") is True

    def test_set_humidity(self):
        b = build_humidifier_set_humidity_command(device_id="d", humidity=55)
        assert _val(b, "hvac_humidity_set") == 55

    def test_set_mode(self):
        b = build_humidifier_set_mode_command(device_id="d", mode="auto")
        assert _val(b, "hvac_air_flow_power") == "auto"


class TestVacuum:
    def test_start(self):
        b = build_vacuum_command(device_id="d", command="start")
        assert _val(b, "vacuum_cleaner_command") == "start"

    def test_return_to_base(self):
        b = build_vacuum_command(device_id="d", command="return_to_base")
        assert _val(b, "vacuum_cleaner_command") == "return_to_base"


class TestSelect:
    def test_select_option(self):
        b = build_select_command(device_id="d", key="sensor_sensitive", option="high")
        assert _val(b, "sensor_sensitive") == "high"


class TestNumber:
    def test_no_scale(self):
        b = build_number_command(device_id="d", key="x", value=80)
        assert _val(b, "x") == 80

    def test_with_scale(self):
        b = build_number_command(device_id="d", key="cur_current", value=0.15, scale=0.001)
        assert _val(b, "cur_current") == 150


class TestButton:
    def test_bool_press(self):
        b = build_button_press_command(device_id="d", key="unlock")
        assert _val(b, "unlock") is True

    def test_enum_press(self):
        b = build_button_press_command(device_id="d", key="action", command_value="reboot")
        assert _val(b, "action") == "reboot"


class TestTV:
    def test_on_off(self):
        b = build_tv_on_off_command(device_id="d", is_on=True)
        assert _val(b, "on_off") is True

    def test_volume_scaling(self):
        b = build_tv_volume_command(device_id="d", volume_level=0.75)
        assert _val(b, "volume_int") == 75

    def test_mute(self):
        b = build_tv_mute_command(device_id="d", mute=True)
        assert _val(b, "mute") is True

    def test_source(self):
        b = build_tv_source_command(device_id="d", source="hdmi2")
        assert _val(b, "source") == "hdmi2"

    def test_custom_key(self):
        b = build_tv_custom_key_command(device_id="d", key="home")
        assert _val(b, "custom_key") == "home"

    def test_direction(self):
        b = build_tv_direction_command(device_id="d", direction="up")
        assert _val(b, "direction") == "up"

    def test_channel(self):
        b = build_tv_channel_command(device_id="d", channel=5)
        assert _val(b, "channel_int") == 5

    def test_volume_step(self):
        b = build_tv_volume_step_command(device_id="d", direction="+")
        assert _val(b, "direction") == "+"
