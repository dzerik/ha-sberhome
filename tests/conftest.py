"""Common fixtures for ha-sberhome tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from homeassistant.config_entries import ConfigEntry

from custom_components.sberhome.const import DOMAIN

MOCK_TOKEN = {
    "access_token": "test_access_token",
    "token_type": "Bearer",
    "expires_in": 3600,
    "refresh_token": "test_refresh_token",
    "id_token": "test_id_token",
}

MOCK_DEVICE_LIGHT = {
    "id": "device_light_1",
    "serial_number": "SN_LIGHT_001",
    "name": {"name": "Test Light"},
    "image_set_type": "bulb_sber",
    "sw_version": "1.0.0",
    "device_info": {
        "manufacturer": "Sber",
        "model": "SBDV-00115",
    },
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "light_mode", "enum_value": "white"},
        {"key": "light_brightness", "integer_value": 500},
        {"key": "light_colour_temp", "integer_value": 50},
        {
            "key": "light_colour",
            "color_value": {"h": 120, "s": 50, "v": 80},
        },
    ],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
    ],
    "attributes": [
        {
            "key": "light_brightness",
            "int_values": {"range": {"min": 1, "max": 900}},
        },
        {
            "key": "light_colour_temp",
            "int_values": {"range": {"min": 0, "max": 100}},
        },
        {
            "key": "light_mode",
            "enum_values": {"values": ["white", "colour"]},
        },
        {
            "key": "light_colour",
            "color_values": {
                "h": {"min": 0, "max": 360},
                "s": {"min": 0, "max": 100},
                "v": {"min": 1, "max": 100},
            },
        },
    ],
}

MOCK_DEVICE_LEDSTRIP = {
    "id": "device_ledstrip_1",
    "serial_number": "SN_LEDSTRIP_001",
    "name": {"name": "Test LED Strip"},
    "image_set_type": "ledstrip_sber",
    "sw_version": "1.0.0",
    "device_info": {
        "manufacturer": "Sber",
        "model": "SBDV-00033",
    },
    "desired_state": [
        {"key": "on_off", "bool_value": False},
        {"key": "light_mode", "enum_value": "colour"},
        {"key": "light_brightness", "integer_value": 300},
        {"key": "light_colour_temp", "integer_value": 30},
        {
            "key": "light_colour",
            "color_value": {"h": 200, "s": 80, "v": 60},
        },
    ],
    "reported_state": [],
    "attributes": [
        {
            "key": "light_brightness",
            "int_values": {"range": {"min": 1, "max": 900}},
        },
        {
            "key": "light_colour_temp",
            "int_values": {"range": {"min": 0, "max": 100}},
        },
        {
            "key": "light_mode",
            "enum_values": {"values": ["white", "colour"]},
        },
        {
            "key": "light_colour",
            "color_values": {
                "h": {"min": 0, "max": 360},
                "s": {"min": 0, "max": 100},
                "v": {"min": 1, "max": 100},
            },
        },
    ],
}

MOCK_DEVICE_SWITCH = {
    "id": "device_switch_1",
    "serial_number": "SN_SWITCH_001",
    "name": {"name": "Test Smart Plug"},
    "image_set_type": "dt_socket_sber",
    "sw_version": "2.0.0",
    "device_info": {
        "manufacturer": "Sber",
        "model": "SBDV-00154",
    },
    "desired_state": [
        {"key": "on_off", "bool_value": True},
    ],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
        # Sber API: voltage/current/power — INTEGER без скейла (V/A/W).
        # Подтверждено через MQTT-SberGate (PR #10).
        {"key": "cur_voltage", "type": "INTEGER", "integer_value": 222},
        {"key": "cur_current", "type": "INTEGER", "integer_value": 1},
        {"key": "cur_power", "type": "INTEGER", "integer_value": 33},
    ],
    "attributes": [],
}

MOCK_DEVICE_CLIMATE_SENSOR = {
    "id": "device_climate_1",
    "serial_number": "SN_CLIMATE_001",
    "name": {"name": "Test Climate Sensor"},
    "image_set_type": "cat_sensor_temp_humidity",
    "sw_version": "1.0.0",
    "device_info": {
        "manufacturer": "Sber",
        "model": "SBDV-00079",
    },
    "desired_state": [],
    "reported_state": [
        {"key": "temperature", "type": "FLOAT", "float_value": 23.5},
        {"key": "humidity", "type": "FLOAT", "float_value": 45.2},
        {"key": "battery_percentage", "type": "INTEGER", "integer_value": 87},
        {"key": "signal_strength", "type": "ENUM", "enum_value": "medium"},
        {"key": "signal_strength_dbm", "type": "INTEGER", "integer_value": -55},
    ],
    "attributes": [],
}

MOCK_DEVICE_WATER_LEAK = {
    "id": "device_water_leak_1",
    "serial_number": "SN_WATER_001",
    "name": {"name": "Test Water Leak"},
    "image_set_type": "dt_sensor_water_leak",
    "sw_version": "1.0.0",
    "device_info": {
        "manufacturer": "Sber",
        "model": "SBDV-00080",
    },
    "desired_state": [],
    "reported_state": [
        {"key": "water_leak_state", "type": "BOOL", "bool_value": False},
        {"key": "battery_percentage", "type": "INTEGER", "integer_value": 95},
        {"key": "battery_low_power", "type": "BOOL", "bool_value": False},
    ],
    "attributes": [],
}

MOCK_DEVICE_DOOR_SENSOR = {
    "id": "device_door_1",
    "serial_number": "SN_DOOR_001",
    "name": {"name": "Test Door Sensor"},
    "image_set_type": "cat_sensor_door",
    "sw_version": "1.0.0",
    "device_info": {
        "manufacturer": "Sber",
        "model": "SBDV-00081",
    },
    "desired_state": [
        {"key": "sensor_sensitive", "enum_value": "auto"},
    ],
    "reported_state": [
        {"key": "doorcontact_state", "type": "BOOL", "bool_value": True},
        {"key": "battery_percentage", "type": "INTEGER", "integer_value": 72},
        {"key": "signal_strength", "type": "ENUM", "enum_value": "high"},
        {"key": "signal_strength_dbm", "type": "INTEGER", "integer_value": -40},
        {"key": "battery_low_power", "type": "BOOL", "bool_value": False},
        {"key": "tamper_alarm", "type": "BOOL", "bool_value": False},
    ],
    "attributes": [
        {"key": "sensor_sensitive", "enum_values": {"values": ["auto", "high"]}},
    ],
}

MOCK_DEVICE_MOTION_SENSOR = {
    "id": "device_motion_1",
    "serial_number": "SN_MOTION_001",
    "name": {"name": "Test Motion Sensor"},
    "image_set_type": "cat_sensor_motion",
    "sw_version": "1.0.0",
    "device_info": {
        "manufacturer": "Sber",
        "model": "SBDV-00082",
    },
    "desired_state": [],
    "reported_state": [
        {"key": "motion_state", "type": "BOOL", "bool_value": False},
        {"key": "battery_percentage", "type": "INTEGER", "integer_value": 100},
    ],
    "attributes": [],
}

MOCK_DEVICE_CURTAIN = {
    "id": "device_curtain_1",
    "serial_number": "SN_CURTAIN_001",
    "name": {"name": "Test Curtain"},
    "image_set_type": "curtain",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-CURTAIN"},
    "desired_state": [
        {"key": "open_set", "integer_value": 50},
        {"key": "open_rate", "enum_value": "auto"},
    ],
    "reported_state": [
        {"key": "open_percentage", "integer_value": 70},
        {"key": "open_state", "enum_value": "opened"},
    ],
    "attributes": [
        {"key": "open_rate", "enum_values": {"values": ["auto", "low", "high"]}},
    ],
}

MOCK_DEVICE_GATE = {
    "id": "device_gate_1",
    "serial_number": "SN_GATE_001",
    "name": {"name": "Test Gate"},
    "image_set_type": "gate",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-GATE"},
    "desired_state": [
        {"key": "open_set", "integer_value": 0},
    ],
    "reported_state": [
        {"key": "open_percentage", "integer_value": 0},
        {"key": "open_state", "enum_value": "closed"},
    ],
    "attributes": [],
}

MOCK_DEVICE_HVAC_AC = {
    "id": "device_hvac_ac_1",
    "serial_number": "SN_AC_001",
    "name": {"name": "Test AC"},
    "image_set_type": "hvac_ac",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-AC"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_temp_set", "integer_value": 24},
        {"key": "hvac_work_mode", "enum_value": "cool"},
        {"key": "hvac_air_flow_power", "enum_value": "auto"},
        {"key": "hvac_air_flow_direction", "enum_value": "top"},
        {"key": "hvac_night_mode", "bool_value": False},
        {"key": "hvac_ionization", "bool_value": False},
        {"key": "hvac_humidity_set", "integer_value": 50},
    ],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "temperature", "float_value": 22.5},
        {"key": "humidity", "float_value": 45.0},
    ],
    "attributes": [
        {
            "key": "hvac_air_flow_direction",
            "enum_values": {"values": ["auto", "top", "middle", "bottom"]},
        },
        {"key": "hvac_night_mode", "bool_values": {}},
        {"key": "hvac_ionization", "bool_values": {}},
    ],
}

MOCK_DEVICE_HVAC_HEATER = {
    "id": "device_hvac_heater_1",
    "serial_number": "SN_HEATER_001",
    "name": {"name": "Test Heater"},
    "image_set_type": "hvac_heater",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-HEATER"},
    "desired_state": [
        {"key": "on_off", "bool_value": False},
        {"key": "hvac_temp_set", "integer_value": 20},
        {"key": "hvac_air_flow_power", "enum_value": "low"},
        {"key": "hvac_thermostat_mode", "enum_value": "auto"},
    ],
    "reported_state": [
        {"key": "temperature", "float_value": 21.0},
    ],
    "attributes": [
        {
            "key": "hvac_thermostat_mode",
            "enum_values": {"values": ["auto", "eco", "comfort", "boost"]},
        },
    ],
}

MOCK_DEVICE_HVAC_RADIATOR = {
    "id": "device_hvac_radiator_1",
    "serial_number": "SN_RAD_001",
    "name": {"name": "Test Radiator"},
    "image_set_type": "hvac_radiator",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-RAD"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_temp_set", "integer_value": 30},
    ],
    "reported_state": [
        {"key": "temperature", "float_value": 27.0},
    ],
    "attributes": [],
}

MOCK_DEVICE_HVAC_BOILER = {
    "id": "device_hvac_boiler_1",
    "serial_number": "SN_BOILER_001",
    "name": {"name": "Test Boiler"},
    "image_set_type": "hvac_boiler",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-BOILER"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_temp_set", "integer_value": 60},
        {"key": "hvac_thermostat_mode", "enum_value": "comfort"},
        {"key": "hvac_heating_rate", "enum_value": "medium"},
    ],
    "reported_state": [
        {"key": "temperature", "float_value": 55.0},
    ],
    "attributes": [
        {
            "key": "hvac_thermostat_mode",
            "enum_values": {"values": ["auto", "eco", "comfort", "boost"]},
        },
        {"key": "hvac_heating_rate", "enum_values": {"values": ["slow", "medium", "fast"]}},
    ],
}

MOCK_DEVICE_HVAC_UNDERFLOOR = {
    "id": "device_hvac_underfloor_1",
    "serial_number": "SN_UF_001",
    "name": {"name": "Test Underfloor"},
    "image_set_type": "hvac_underfloor",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-UF"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_temp_set", "integer_value": 35},
        {"key": "hvac_thermostat_mode", "enum_value": "eco"},
        {"key": "hvac_heating_rate", "enum_value": "slow"},
    ],
    "reported_state": [
        {"key": "temperature", "float_value": 30.0},
    ],
    "attributes": [
        {
            "key": "hvac_thermostat_mode",
            "enum_values": {"values": ["auto", "eco", "comfort", "boost"]},
        },
        {"key": "hvac_heating_rate", "enum_values": {"values": ["slow", "medium", "fast"]}},
    ],
}

MOCK_DEVICE_HVAC_AIR_PURIFIER = {
    "id": "device_hvac_purifier_1",
    "serial_number": "SN_PURIFIER_001",
    "name": {"name": "Test Air Purifier"},
    "image_set_type": "hvac_air_purifier",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-PURIFIER"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_air_flow_power", "enum_value": "low"},
        {"key": "hvac_night_mode", "bool_value": False},
        {"key": "hvac_ionization", "bool_value": True},
        {"key": "hvac_aromatization", "bool_value": False},
        {"key": "hvac_decontaminate", "bool_value": False},
    ],
    "reported_state": [
        {"key": "hvac_replace_filter", "bool_value": False},
        {"key": "hvac_replace_ionizator", "bool_value": False},
    ],
    "attributes": [
        {"key": "hvac_night_mode", "bool_values": {}},
        {"key": "hvac_ionization", "bool_values": {}},
        {"key": "hvac_aromatization", "bool_values": {}},
        {"key": "hvac_decontaminate", "bool_values": {}},
    ],
}

MOCK_DEVICE_INTERCOM = {
    "id": "device_intercom_1",
    "serial_number": "SN_INTERCOM_001",
    "name": {"name": "Test Intercom"},
    "image_set_type": "intercom",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-INTERCOM"},
    "desired_state": [],
    "reported_state": [
        {"key": "online", "bool_value": True},
        {"key": "incoming_call", "bool_value": False},
    ],
    "attributes": [],
}

MOCK_DEVICE_SENSOR_GAS = {
    "id": "device_gas_1",
    "serial_number": "SN_GAS_001",
    "name": {"name": "Test Gas Sensor"},
    "image_set_type": "sensor_gas",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-GAS"},
    "desired_state": [
        {"key": "sensor_sensitive", "enum_value": "high"},
        {"key": "alarm_mute", "bool_value": False},
    ],
    "reported_state": [
        {"key": "gas_leak_state", "bool_value": False},
    ],
    "attributes": [
        {"key": "sensor_sensitive", "enum_values": {"values": ["auto", "high"]}},
        {"key": "alarm_mute", "bool_values": {}},
    ],
}

MOCK_DEVICE_SENSOR_SMOKE = {
    "id": "device_smoke_1",
    "serial_number": "SN_SMOKE_001",
    "name": {"name": "Test Smoke Sensor"},
    "image_set_type": "sensor_smoke",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-SMOKE"},
    "desired_state": [
        {"key": "alarm_mute", "bool_value": False},
    ],
    "reported_state": [
        {"key": "smoke_state", "bool_value": False},
    ],
    "attributes": [
        {"key": "alarm_mute", "bool_values": {}},
    ],
}

MOCK_DEVICE_SENSOR_PIR_SENS = {
    "id": "device_pir_sens_1",
    "serial_number": "SN_PIR_SENS_001",
    "name": {"name": "Test PIR Sensitive"},
    "image_set_type": "sensor_pir",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-PIR"},
    "desired_state": [
        {"key": "sensor_sensitive", "enum_value": "auto"},
    ],
    "reported_state": [
        {"key": "motion_state", "bool_value": False},
    ],
    "attributes": [
        {"key": "sensor_sensitive", "enum_values": {"values": ["auto", "high"]}},
    ],
}

MOCK_DEVICE_SENSOR_DOOR_SENS = {
    "id": "device_door_sens_1",
    "serial_number": "SN_DOOR_SENS_001",
    "name": {"name": "Test Door Sensitive"},
    "image_set_type": "sensor_door",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-DOOR"},
    "desired_state": [
        {"key": "sensor_sensitive", "enum_value": "high"},
    ],
    "reported_state": [
        {"key": "doorcontact_state", "bool_value": False},
    ],
    "attributes": [
        {"key": "sensor_sensitive", "enum_values": {"values": ["auto", "high"]}},
    ],
}

MOCK_DEVICE_WINDOW_BLIND = {
    "id": "device_blind_1",
    "serial_number": "SN_BLIND_001",
    "name": {"name": "Test Blind"},
    "image_set_type": "window_blind",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-BLIND"},
    "desired_state": [
        {"key": "open_set", "integer_value": 40},
        {"key": "light_transmission_percentage", "integer_value": 60},
    ],
    "reported_state": [
        {"key": "open_percentage", "integer_value": 40},
        {"key": "open_state", "enum_value": "opened"},
    ],
    "attributes": [],
}

MOCK_DEVICE_HVAC_FAN = {
    "id": "device_hvac_fan_1",
    "serial_number": "SN_FAN_001",
    "name": {"name": "Test Fan"},
    "image_set_type": "hvac_fan",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-FAN"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_air_flow_power", "enum_value": "medium"},
    ],
    "reported_state": [],
    "attributes": [],
}

MOCK_DEVICE_HUMIDIFIER = {
    "id": "device_humidifier_1",
    "serial_number": "SN_HUMID_001",
    "name": {"name": "Test Humidifier"},
    "image_set_type": "hvac_humidifier",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-HUMID"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "hvac_humidity_set", "integer_value": 55},
        {"key": "hvac_night_mode", "bool_value": False},
        {"key": "hvac_ionization", "bool_value": False},
        {"key": "hvac_air_flow_power", "enum_value": "medium"},
    ],
    "reported_state": [
        {"key": "humidity", "float_value": 50.0},
        {"key": "hvac_water_level", "integer_value": 75},
        {"key": "hvac_water_percentage", "integer_value": 80},
        {"key": "hvac_water_low_level", "bool_value": False},
        {"key": "hvac_replace_filter", "bool_value": False},
        {"key": "hvac_replace_ionizator", "bool_value": False},
    ],
    "attributes": [
        {"key": "hvac_night_mode", "bool_values": {}},
        {"key": "hvac_ionization", "bool_values": {}},
    ],
}

MOCK_DEVICE_KETTLE = {
    "id": "device_kettle_1",
    "serial_number": "SN_KETTLE_001",
    "name": {"name": "Test Kettle"},
    "image_set_type": "kettle",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-KETTLE"},
    "desired_state": [
        {"key": "on_off", "bool_value": False},
        {"key": "kitchen_water_temperature_set", "integer_value": 80},
        {"key": "child_lock", "bool_value": False},
    ],
    "reported_state": [
        {"key": "kitchen_water_temperature", "integer_value": 55},
        {"key": "kitchen_water_low_level", "bool_value": False},
    ],
    "attributes": [
        {"key": "child_lock", "bool_values": {}},
    ],
}

MOCK_DEVICE_TV = {
    "id": "device_tv_1",
    "serial_number": "SN_TV_001",
    "name": {"name": "Test TV"},
    "image_set_type": "tv",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-TV"},
    "desired_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "source", "enum_value": "hdmi1"},
        {"key": "volume_int", "integer_value": 40},
        {"key": "mute", "bool_value": False},
    ],
    "reported_state": [],
    "attributes": [],
}

MOCK_DEVICE_VACUUM = {
    "id": "device_vacuum_1",
    "serial_number": "SN_VACUUM_001",
    "name": {"name": "Test Vacuum"},
    "image_set_type": "vacuum_cleaner",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-VACUUM"},
    "desired_state": [
        {"key": "vacuum_cleaner_program", "enum_value": "smart"},
        {"key": "child_lock", "bool_value": False},
    ],
    "reported_state": [
        {"key": "vacuum_cleaner_status", "enum_value": "cleaning"},
        {"key": "battery_percentage", "integer_value": 67},
    ],
    "attributes": [
        {
            "key": "vacuum_cleaner_program",
            "enum_values": {"values": ["perimeter", "spot", "smart"]},
        },
        {"key": "child_lock", "bool_values": {}},
    ],
}

MOCK_DEVICE_SCENARIO_BUTTON = {
    "id": "device_scenario_1",
    "serial_number": "SN_SCENARIO_001",
    "name": {"name": "Test Button"},
    "image_set_type": "scenario_button",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-SCENARIO"},
    "desired_state": [],
    "reported_state": [
        {"key": "button_1_event", "enum_value": "click", "timestamp": "2024-01-01T00:00:00Z"},
        {
            "key": "button_2_event",
            "enum_value": "double_click",
            "timestamp": "2024-01-01T00:00:00Z",
        },
    ],
    "attributes": [],
}

MOCK_DEVICE_HUB = {
    "id": "device_hub_1",
    "serial_number": "SN_HUB_001",
    "name": {"name": "Test Hub"},
    "image_set_type": "hub",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-HUB"},
    "desired_state": [],
    "reported_state": [
        {"key": "online", "bool_value": True},
    ],
    "attributes": [],
}

MOCK_DEVICE_TREE = {
    "devices": [MOCK_DEVICE_LIGHT, MOCK_DEVICE_SWITCH],
    "children": [
        {
            "devices": [MOCK_DEVICE_LEDSTRIP],
            "children": [],
        }
    ],
}


@pytest.fixture
def mock_devices_extra() -> dict:
    """Extended devices dict including new categories (cover/climate/fan/humidifier/kettle/tv/vacuum/scenario/hub)."""
    return {
        "device_curtain_1": MOCK_DEVICE_CURTAIN,
        "device_gate_1": MOCK_DEVICE_GATE,
        "device_hvac_ac_1": MOCK_DEVICE_HVAC_AC,
        "device_hvac_heater_1": MOCK_DEVICE_HVAC_HEATER,
        "device_hvac_radiator_1": MOCK_DEVICE_HVAC_RADIATOR,
        "device_hvac_boiler_1": MOCK_DEVICE_HVAC_BOILER,
        "device_hvac_underfloor_1": MOCK_DEVICE_HVAC_UNDERFLOOR,
        "device_hvac_fan_1": MOCK_DEVICE_HVAC_FAN,
        "device_humidifier_1": MOCK_DEVICE_HUMIDIFIER,
        "device_hvac_purifier_1": MOCK_DEVICE_HVAC_AIR_PURIFIER,
        "device_kettle_1": MOCK_DEVICE_KETTLE,
        "device_tv_1": MOCK_DEVICE_TV,
        "device_vacuum_1": MOCK_DEVICE_VACUUM,
        "device_scenario_1": MOCK_DEVICE_SCENARIO_BUTTON,
        "device_hub_1": MOCK_DEVICE_HUB,
        "device_intercom_1": MOCK_DEVICE_INTERCOM,
        "device_gas_1": MOCK_DEVICE_SENSOR_GAS,
        "device_smoke_1": MOCK_DEVICE_SENSOR_SMOKE,
        "device_pir_sens_1": MOCK_DEVICE_SENSOR_PIR_SENS,
        "device_door_sens_1": MOCK_DEVICE_SENSOR_DOOR_SENS,
        "device_blind_1": MOCK_DEVICE_WINDOW_BLIND,
    }


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.version = 1
    entry.minor_version = 1
    entry.domain = DOMAIN
    entry.title = "SberHome"
    entry.data = {"token": MOCK_TOKEN}
    entry.options = {}
    entry.source = "user"
    entry.entry_id = "test_entry_id"
    entry.runtime_data = None
    return entry


@pytest.fixture
def mock_devices() -> dict:
    """Return mock devices dict (as returned by extract_devices)."""
    return {
        "device_light_1": MOCK_DEVICE_LIGHT,
        "device_ledstrip_1": MOCK_DEVICE_LEDSTRIP,
        "device_switch_1": MOCK_DEVICE_SWITCH,
        "device_climate_1": MOCK_DEVICE_CLIMATE_SENSOR,
        "device_water_leak_1": MOCK_DEVICE_WATER_LEAK,
        "device_door_1": MOCK_DEVICE_DOOR_SENSOR,
        "device_motion_1": MOCK_DEVICE_MOTION_SENSOR,
    }


def build_coordinator_caches(raw_devices: dict) -> tuple[dict, dict]:
    """Helper для тестов: построить (devices_dto, entities) из raw mock_devices.

    Используется тестами платформ, мигрированных на sbermap (PR #3-#7).
    """
    from custom_components.sberhome.aiosber.dto.device import DeviceDto
    from custom_components.sberhome.sbermap import map_device_to_entities

    devices: dict = {}
    entities: dict = {}
    for did, raw in raw_devices.items():
        dto = DeviceDto.from_dict(raw)
        if dto is None:
            continue
        devices[did] = dto
        entities[did] = map_device_to_entities(dto)
    return devices, entities


@pytest.fixture
def mock_coordinator_with_entities(mock_devices):
    """Coordinator-like MagicMock с заполненными data/devices/entities.

    Готовый «батарейки в комплекте» mock для тестов sbermap-driven платформ.
    """
    coord = MagicMock()
    coord.data = mock_devices
    coord.devices, coord.entities = build_coordinator_caches(mock_devices)
    return coord
