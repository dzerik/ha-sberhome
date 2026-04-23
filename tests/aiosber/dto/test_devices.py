"""Тесты типизированных wrappers (LightDevice, SocketDevice, ...)."""

from __future__ import annotations

import pytest

from custom_components.sberhome.aiosber import (
    TypedDevice,
    as_typed,
)
from custom_components.sberhome.aiosber.dto import DeviceDto
from custom_components.sberhome.aiosber.dto.devices import (
    AirConditionerDevice,
    AirPurifierDevice,
    BoilerDevice,
    CurtainDevice,
    DoorSensorDevice,
    FanDevice,
    GasSensorDevice,
    GateDevice,
    HeaterDevice,
    HubDevice,
    HumidifierDevice,
    IntercomDevice,
    KettleDevice,
    LedStripDevice,
    LightDevice,
    MotionSensorDevice,
    RadiatorDevice,
    RelayDevice,
    ScenarioButtonDevice,
    SmokeSensorDevice,
    SocketDevice,
    TemperatureSensorDevice,
    TvDevice,
    UnderfloorHeatingDevice,
    VacuumDevice,
    ValveDevice,
    WaterLeakSensorDevice,
    WindowBlindDevice,
    all_categories,
    class_for_category,
)


def _dto(image_set_type: str, reported: list[dict] | None = None, **extra) -> DeviceDto:
    raw = {
        "id": "test-id",
        "name": "Test",
        "image_set_type": image_set_type,
        "reported_state": reported or [],
        **extra,
    }
    d = DeviceDto.from_dict(raw)
    assert d is not None
    return d


# ============== Coverage check ==============
def test_all_28_categories_covered():
    """Все 28 категорий из spec должны иметь typed wrapper."""
    cats = all_categories()
    assert len(cats) == 28
    expected = {
        "light",
        "led_strip",
        "socket",
        "relay",
        "sensor_temp",
        "sensor_water_leak",
        "sensor_door",
        "sensor_pir",
        "sensor_smoke",
        "sensor_gas",
        "curtain",
        "window_blind",
        "gate",
        "valve",
        "hvac_ac",
        "hvac_heater",
        "hvac_radiator",
        "hvac_boiler",
        "hvac_underfloor_heating",
        "hvac_fan",
        "hvac_air_purifier",
        "hvac_humidifier",
        "kettle",
        "vacuum_cleaner",
        "tv",
        "scenario_button",
        "intercom",
        "hub",
    }
    assert cats == expected


def test_class_for_category_lookup():
    assert class_for_category("light") is LightDevice
    assert class_for_category("hvac_ac") is AirConditionerDevice
    assert class_for_category("nonexistent") is None


# ============== as_typed dispatch ==============
def test_as_typed_returns_specific_class():
    d = _dto("light")
    assert isinstance(as_typed(d), LightDevice)
    d = _dto("hvac_ac")
    assert isinstance(as_typed(d), AirConditionerDevice)


def test_as_typed_substring_match():
    """Image_set_type с префиксом → substring-match."""
    d = _dto("dt_socket_sber")
    typed = as_typed(d)
    assert isinstance(typed, SocketDevice)


def test_as_typed_unknown_returns_base():
    d = _dto("brand_new_category_xyz")
    typed = as_typed(d)
    assert type(typed) is TypedDevice


# ============== TypedDevice base ==============
def test_base_proxies():
    d = _dto(
        "light",
        name="Кухня",
        serial_number="SN1",
        sw_version="2.0",
        reported=[
            {"key": "online", "type": "BOOL", "bool_value": True},
            {"key": "battery_percentage", "type": "INTEGER", "integer_value": 85},
            {"key": "battery_low_power", "type": "BOOL", "bool_value": False},
        ],
    )
    t = TypedDevice(d)
    assert t.id == "test-id"
    assert t.name == "Кухня"
    assert t.serial_number == "SN1"
    assert t.sw_version == "2.0"
    assert t.online is True
    assert t.battery_percentage == 85
    assert t.battery_low is False


def test_base_has_feature():
    d = _dto("light", reported=[{"key": "on_off", "type": "BOOL", "bool_value": True}])
    t = TypedDevice(d)
    assert t.has_feature("on_off") is True
    assert t.has_feature("nonexistent") is False


def test_base_repr():
    d = _dto("light", reported=[{"key": "online", "type": "BOOL", "bool_value": True}])
    r = repr(TypedDevice(d))
    assert "TypedDevice" in r
    assert "test-id" in r


# ============== LightDevice ==============
class TestLightDevice:
    def test_basic_properties(self):
        d = _dto(
            "light",
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "light_brightness", "type": "INTEGER", "integer_value": 750},
                {"key": "light_colour_temp", "type": "INTEGER", "integer_value": 50},
                {"key": "light_mode", "type": "ENUM", "enum_value": "white"},
            ],
        )
        t = LightDevice(d)
        assert t.is_on is True
        assert t.brightness == 750
        assert t.color_temp == 50
        assert t.mode == "white"

    def test_color_value(self):
        d = _dto(
            "light",
            reported=[
                {
                    "key": "light_colour",
                    "type": "COLOR",
                    "color_value": {"hue": 200, "saturation": 80, "brightness": 70},
                }
            ],
        )
        t = LightDevice(d)
        c = t.color
        assert c is not None
        assert c.hue == 200
        assert c.saturation == 80


class TestLedStripDevice:
    def test_inherits_light_features(self):
        d = _dto(
            "led_strip",
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "sleep_timer", "type": "INTEGER", "integer_value": 30},
            ],
        )
        t = LedStripDevice(d)
        assert t.is_on is True
        assert t.sleep_timer == 30


# ============== SocketDevice / RelayDevice ==============
class TestSocketDevice:
    def test_power_monitoring(self):
        d = _dto(
            "socket",
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "voltage", "type": "INTEGER", "integer_value": 230},
                {"key": "current", "type": "INTEGER", "integer_value": 1500},  # mA
                {"key": "power", "type": "INTEGER", "integer_value": 345},
                {"key": "child_lock", "type": "BOOL", "bool_value": True},
            ],
        )
        t = SocketDevice(d)
        assert t.is_on is True
        assert t.voltage == 230
        assert t.current_milliamps == 1500
        assert t.current_amps == 1.5
        assert t.power_watts == 345
        assert t.child_lock is True

    def test_cur_prefix_fallback(self):
        d = _dto(
            "socket",
            reported=[
                {"key": "cur_voltage", "type": "INTEGER", "integer_value": 220},
            ],
        )
        assert SocketDevice(d).voltage == 220


class TestRelayDevice:
    def test_no_child_lock(self):
        d = _dto(
            "relay",
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
            ],
        )
        t = RelayDevice(d)
        assert t.is_on is True
        assert not hasattr(t, "child_lock")


# ============== Sensors ==============
class TestSensors:
    def test_temperature_sensor(self):
        d = _dto(
            "sensor_temp",
            reported=[
                {"key": "temperature", "type": "FLOAT", "float_value": 22.5},
                {"key": "humidity", "type": "INTEGER", "integer_value": 60},
                {"key": "air_pressure", "type": "INTEGER", "integer_value": 1013},
            ],
        )
        t = TemperatureSensorDevice(d)
        assert t.temperature == 22.5
        assert t.humidity == 60
        assert t.air_pressure == 1013

    def test_water_leak(self):
        d = _dto(
            "sensor_water_leak",
            reported=[
                {"key": "water_leak_state", "type": "BOOL", "bool_value": True},
            ],
        )
        assert WaterLeakSensorDevice(d).water_leak is True

    def test_door_sensor(self):
        d = _dto(
            "sensor_door",
            reported=[
                {"key": "doorcontact_state", "type": "BOOL", "bool_value": True},
                {"key": "tamper_alarm", "type": "BOOL", "bool_value": False},
            ],
        )
        t = DoorSensorDevice(d)
        assert t.is_open is True
        assert t.tamper_alarm is False

    def test_motion_sensor_pir(self):
        d = _dto("sensor_pir", reported=[{"key": "pir", "type": "BOOL", "bool_value": True}])
        assert MotionSensorDevice(d).motion is True

    def test_motion_sensor_motion_state_fallback(self):
        d = _dto(
            "sensor_pir",
            reported=[
                {"key": "motion_state", "type": "BOOL", "bool_value": True},
            ],
        )
        assert MotionSensorDevice(d).motion is True

    def test_smoke(self):
        d = _dto(
            "sensor_smoke",
            reported=[
                {"key": "smoke_state", "type": "BOOL", "bool_value": False},
                {"key": "alarm_mute", "type": "BOOL", "bool_value": True},
            ],
        )
        t = SmokeSensorDevice(d)
        assert t.smoke is False
        assert t.alarm_muted is True

    def test_gas(self):
        d = _dto(
            "sensor_gas",
            reported=[
                {"key": "gas_leak_state", "type": "BOOL", "bool_value": True},
                {"key": "sensor_sensitive", "type": "ENUM", "enum_value": "high"},
            ],
        )
        t = GasSensorDevice(d)
        assert t.gas_leak is True
        assert t.sensitivity == "high"


# ============== Covers ==============
class TestCovers:
    def test_curtain_basic(self):
        d = _dto(
            "curtain",
            reported=[
                {"key": "open_percentage", "type": "INTEGER", "integer_value": 75},
                {"key": "open_state", "type": "ENUM", "enum_value": "opening"},
                {"key": "open_rate", "type": "ENUM", "enum_value": "low"},
            ],
        )
        t = CurtainDevice(d)
        assert t.position == 75
        assert t.state == "opening"
        assert t.is_opening is True
        assert t.is_open is False  # state != "open"
        assert t.open_rate == "low"

    def test_curtain_double_panel(self):
        d = _dto(
            "curtain",
            reported=[
                {"key": "open_left_set", "type": "INTEGER", "integer_value": 80},
                {"key": "open_left_percentage", "type": "INTEGER", "integer_value": 80},
                {"key": "open_right_set", "type": "INTEGER", "integer_value": 30},
                {"key": "open_right_percentage", "type": "INTEGER", "integer_value": 30},
            ],
        )
        t = CurtainDevice(d)
        assert t.has_left_panel is True
        assert t.has_right_panel is True
        assert t.left_position == 80
        assert t.right_position == 30

    def test_window_blind(self):
        d = _dto(
            "window_blind",
            reported=[
                {"key": "open_percentage", "type": "INTEGER", "integer_value": 0},
            ],
        )
        assert WindowBlindDevice(d).position == 0

    def test_gate(self):
        d = _dto(
            "gate",
            reported=[
                {"key": "open_state", "type": "ENUM", "enum_value": "closed"},
            ],
        )
        t = GateDevice(d)
        assert t.state == "closed"

    def test_valve(self):
        d = _dto(
            "valve",
            reported=[
                {"key": "open_state", "type": "ENUM", "enum_value": "open"},
            ],
        )
        assert ValveDevice(d).is_open is True


# ============== HVAC ==============
class TestHvac:
    def test_air_conditioner(self):
        d = _dto(
            "hvac_ac",
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "hvac_temp_set", "type": "INTEGER", "integer_value": 22},
                {"key": "temperature", "type": "FLOAT", "float_value": 24.5},
                {"key": "hvac_work_mode", "type": "ENUM", "enum_value": "cool"},
                {"key": "hvac_air_flow_power", "type": "ENUM", "enum_value": "high"},
                {"key": "hvac_night_mode", "type": "BOOL", "bool_value": False},
            ],
        )
        t = AirConditionerDevice(d)
        assert t.is_on is True
        assert t.target_temperature == 22
        assert t.current_temperature == 24.5
        assert t.work_mode == "cool"
        assert t.fan_speed == "high"
        assert t.night_mode is False

    def test_heater_thermostat_mode(self):
        d = _dto(
            "hvac_heater",
            reported=[
                {"key": "hvac_thermostat_mode", "type": "ENUM", "enum_value": "comfort"},
            ],
        )
        assert HeaterDevice(d).thermostat_mode == "comfort"

    def test_radiator_inherits_base(self):
        d = _dto(
            "hvac_radiator",
            reported=[
                {"key": "hvac_temp_set", "type": "INTEGER", "integer_value": 35},
            ],
        )
        assert RadiatorDevice(d).target_temperature == 35

    def test_boiler_heating_rate(self):
        d = _dto(
            "hvac_boiler",
            reported=[
                {"key": "hvac_temp_set", "type": "INTEGER", "integer_value": 60},
                {"key": "hvac_heating_rate", "type": "ENUM", "enum_value": "high"},
            ],
        )
        t = BoilerDevice(d)
        assert t.target_temperature == 60
        assert t.heating_rate == "high"

    def test_underfloor(self):
        d = _dto(
            "hvac_underfloor_heating",
            reported=[
                {"key": "hvac_temp_set", "type": "INTEGER", "integer_value": 30},
            ],
        )
        assert UnderfloorHeatingDevice(d).target_temperature == 30

    def test_fan_speed(self):
        d = _dto(
            "hvac_fan",
            reported=[
                {"key": "hvac_air_flow_power", "type": "ENUM", "enum_value": "turbo"},
            ],
        )
        assert FanDevice(d).speed == "turbo"

    def test_air_purifier(self):
        d = _dto(
            "hvac_air_purifier",
            reported=[
                {"key": "hvac_ionization", "type": "BOOL", "bool_value": True},
                {"key": "hvac_replace_filter", "type": "BOOL", "bool_value": True},
            ],
        )
        t = AirPurifierDevice(d)
        assert t.ionization is True
        assert t.replace_filter_alarm is True

    def test_humidifier(self):
        d = _dto(
            "hvac_humidifier",
            reported=[
                {"key": "humidity", "type": "INTEGER", "integer_value": 45},
                {"key": "hvac_humidity_set", "type": "INTEGER", "integer_value": 60},
                {"key": "hvac_water_level", "type": "INTEGER", "integer_value": 80},
            ],
        )
        t = HumidifierDevice(d)
        assert t.humidity == 45
        assert t.target_humidity == 60
        assert t.water_level == 80


# ============== Appliances ==============
class TestAppliances:
    def test_kettle(self):
        d = _dto(
            "kettle",
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "kitchen_water_temperature", "type": "FLOAT", "float_value": 85.5},
                {"key": "kitchen_water_temperature_set", "type": "INTEGER", "integer_value": 100},
                {"key": "kitchen_water_level", "type": "INTEGER", "integer_value": 60},
                {"key": "child_lock", "type": "BOOL", "bool_value": True},
            ],
        )
        t = KettleDevice(d)
        assert t.is_on is True
        assert t.water_temperature == 85.5
        assert t.target_water_temperature == 100
        assert t.water_level == 60
        assert t.child_lock is True

    def test_vacuum(self):
        d = _dto(
            "vacuum_cleaner",
            reported=[
                {"key": "vacuum_cleaner_status", "type": "ENUM", "enum_value": "cleaning"},
                {"key": "vacuum_cleaner_program", "type": "ENUM", "enum_value": "smart"},
            ],
        )
        t = VacuumDevice(d)
        assert t.status == "cleaning"
        assert t.program == "smart"

    def test_tv(self):
        d = _dto(
            "tv",
            reported=[
                {"key": "on_off", "type": "BOOL", "bool_value": True},
                {"key": "source", "type": "ENUM", "enum_value": "hdmi1"},
                {"key": "volume_int", "type": "INTEGER", "integer_value": 35},
                {"key": "mute", "type": "BOOL", "bool_value": False},
                {"key": "channel_int", "type": "INTEGER", "integer_value": 5},
            ],
        )
        t = TvDevice(d)
        assert t.is_on is True
        assert t.source == "hdmi1"
        assert t.volume == 35
        assert t.muted is False
        assert t.channel == 5


# ============== Misc ==============
class TestMisc:
    def test_scenario_button_event(self):
        d = _dto(
            "scenario_button",
            reported=[
                {"key": "button_1_event", "type": "ENUM", "enum_value": "click"},
                {"key": "button_3_event", "type": "ENUM", "enum_value": "double_click"},
            ],
        )
        t = ScenarioButtonDevice(d)
        assert t.button_event(1) == "click"
        assert t.button_event(3) == "double_click"
        assert t.button_event(2) is None

    def test_scenario_button_invalid_index(self):
        d = _dto("scenario_button")
        t = ScenarioButtonDevice(d)
        with pytest.raises(ValueError):
            t.button_event(11)

    def test_scenario_button_directional(self):
        d = _dto(
            "scenario_button",
            reported=[
                {"key": "button_top_left_event", "type": "ENUM", "enum_value": "click"},
            ],
        )
        t = ScenarioButtonDevice(d)
        assert t.directional_event("top_left") == "click"
        with pytest.raises(ValueError):
            t.directional_event("middle")

    def test_intercom(self):
        d = _dto(
            "intercom",
            reported=[
                {"key": "incoming_call", "type": "BOOL", "bool_value": True},
            ],
        )
        t = IntercomDevice(d)
        assert t.has_incoming_call is True

    def test_hub(self):
        d = _dto("hub", reported=[{"key": "online", "type": "BOOL", "bool_value": True}])
        t = HubDevice(d)
        assert t.online is True


# ============================================================================
# Coverage gap closures — добавлено после внутреннего audit'а.
# ============================================================================


class TestGateExtended:
    """gate: open_left_*/open_right_*/open_rate (закрытие spec gap)."""

    def test_gate_open_rate(self):
        d = _dto(
            "gate",
            reported=[
                {"key": "open_rate", "type": "ENUM", "enum_value": "high"},
            ],
        )
        assert GateDevice(d).open_rate == "high"

    def test_gate_double_panel(self):
        d = _dto(
            "gate",
            reported=[
                {"key": "open_left_set", "type": "INTEGER", "integer_value": 100},
                {"key": "open_left_percentage", "type": "INTEGER", "integer_value": 60},
                {"key": "open_right_set", "type": "INTEGER", "integer_value": 100},
                {"key": "open_right_percentage", "type": "INTEGER", "integer_value": 40},
            ],
        )
        g = GateDevice(d)
        assert g.has_left_panel and g.has_right_panel
        assert g.left_position == 60
        assert g.right_position == 40


class TestHumidifierExtended:
    """hvac_humidifier: replace_filter/replace_ionizer/water_percentage."""

    def test_humidifier_replace_alarms(self):
        d = _dto(
            "hvac_humidifier",
            reported=[
                {"key": "hvac_replace_filter", "type": "BOOL", "bool_value": True},
                {"key": "hvac_replace_ionizator", "type": "BOOL", "bool_value": False},
                {"key": "hvac_water_percentage", "type": "INTEGER", "integer_value": 75},
            ],
        )
        h = HumidifierDevice(d)
        assert h.replace_filter_alarm is True
        assert h.replace_ionizer_alarm is False
        assert h.water_percentage == 75


class TestAirPurifierDecontaminate:
    def test_decontaminate(self):
        d = _dto(
            "hvac_air_purifier",
            reported=[
                {"key": "hvac_decontaminate", "type": "BOOL", "bool_value": True},
            ],
        )
        assert AirPurifierDevice(d).decontaminate is True


class TestValveFaultAlarm:
    def test_valve_fault_alarm(self):
        d = _dto(
            "valve",
            reported=[
                {"key": "fault_alarm", "type": "ENUM", "enum_value": "alarm"},
            ],
        )
        assert ValveDevice(d).fault_alarm == "alarm"


class TestSocketUpperCurrent:
    def test_upper_current_threshold(self):
        d = _dto(
            "socket",
            reported=[
                {"key": "upper_current_threshold", "type": "INTEGER", "integer_value": 16000},
            ],
        )
        assert SocketDevice(d).upper_current_threshold == 16000


class TestIntercomConfig:
    def test_virtual_open_state(self):
        d = _dto(
            "intercom",
            reported=[
                {"key": "virtual_open_state", "type": "BOOL", "bool_value": True},
                {"key": "unlock_duration", "type": "INTEGER", "integer_value": 5},
            ],
        )
        i = IntercomDevice(d)
        assert i.virtual_open_state is True
        assert i.unlock_duration == 5


class TestScenarioButtonConfig:
    def test_led_indicators(self):
        d = _dto(
            "scenario_button",
            reported=[
                {"key": "led_indicator_on", "type": "BOOL", "bool_value": True},
                {"key": "led_indicator_off", "type": "BOOL", "bool_value": False},
                {"key": "is_double_click_enabled", "type": "BOOL", "bool_value": True},
                {"key": "click_mode", "type": "ENUM", "enum_value": "both"},
            ],
        )
        s = ScenarioButtonDevice(d)
        assert s.led_indicator_on is True
        assert s.led_indicator_off is False
        assert s.is_double_click_enabled is True
        assert s.click_mode == "both"

    def test_color_indicator_hsv(self):
        d = _dto(
            "scenario_button",
            reported=[
                {
                    "key": "color_indicator_on",
                    "type": "COLOR",
                    "color_value": {"hue": 120, "saturation": 100, "brightness": 50},
                }
            ],
        )
        s = ScenarioButtonDevice(d)
        c = s.color_indicator_on
        assert c is not None
        assert c.hue == 120


class TestCoversConfig:
    def test_curtain_show_setup(self):
        d = _dto(
            "curtain",
            reported=[
                {"key": "show_setup", "type": "BOOL", "bool_value": True},
            ],
        )
        assert CurtainDevice(d).show_setup is True

    def test_window_blind_light_transmission(self):
        d = _dto(
            "window_blind",
            reported=[
                {"key": "light_transmission_percentage", "type": "INTEGER", "integer_value": 50},
            ],
        )
        assert WindowBlindDevice(d).light_transmission == 50

    def test_open_close_mixin_extras(self):
        """reverse_mode/opening_time/calibration через _OpenCloseMixin."""
        d = _dto(
            "curtain",
            reported=[
                {"key": "reverse_mode", "type": "BOOL", "bool_value": True},
                {"key": "opening_time", "type": "INTEGER", "integer_value": 30},
                {"key": "calibration", "type": "ENUM", "enum_value": "calibrating"},
            ],
        )
        c = CurtainDevice(d)
        assert c.reverse_mode is True
        assert c.opening_time == 30
        assert c.calibration == "calibrating"


class TestThermostatMixin:
    """Большой config-набор Thermostat (RadiatorDevice/BoilerDevice/UnderfloorHeatingDevice)."""

    def test_radiator_thermostat_fields(self):
        d = _dto(
            "hvac_radiator",
            reported=[
                {"key": "min_temperature", "type": "INTEGER", "integer_value": 25},
                {"key": "max_temperature", "type": "INTEGER", "integer_value": 40},
                {"key": "device_condition", "type": "ENUM", "enum_value": "warm"},
                {"key": "heating_hysteresis", "type": "INTEGER", "integer_value": 5},
                {"key": "anti_frost_temp", "type": "INTEGER", "integer_value": 7},
                {"key": "open_window", "type": "BOOL", "bool_value": True},
                {"key": "open_window_status", "type": "BOOL", "bool_value": False},
                {"key": "floor_type", "type": "ENUM", "enum_value": "tile"},
                {"key": "floor_sensor_type", "type": "ENUM", "enum_value": "NTC10k"},
                {"key": "main_sensor", "type": "ENUM", "enum_value": "CL"},
                {"key": "child_lock", "type": "BOOL", "bool_value": True},
                {"key": "adjust_floor_temp", "type": "BOOL", "bool_value": False},
            ],
        )
        r = RadiatorDevice(d)
        assert r.min_temperature == 25
        assert r.max_temperature == 40
        assert r.device_condition == "warm"
        assert r.heating_hysteresis == 5
        assert r.anti_frost_temp == 7
        assert r.open_window is True
        assert r.open_window_status is False
        assert r.floor_type == "tile"
        assert r.floor_sensor_type == "NTC10k"
        assert r.main_sensor == "CL"
        assert r.child_lock is True
        assert r.adjust_floor_temp is False

    def test_boiler_schedule(self):
        d = _dto(
            "hvac_boiler",
            reported=[
                {
                    "key": "schedule",
                    "type": "SCHEDULE",
                    "schedule_value": {
                        "days": ["monday", "tuesday"],
                        "events": [
                            {"time": "07:00", "value_type": "FLOAT", "target_value": 23.0},
                        ],
                    },
                }
            ],
        )
        b = BoilerDevice(d)
        sched = b.schedule
        assert sched is not None
        assert "monday" in [d.value for d in sched.days]
        assert len(sched.events) == 1

    def test_boiler_schedule_status(self):
        d = _dto(
            "hvac_boiler",
            reported=[
                {"key": "schedule_status", "type": "ENUM", "enum_value": "active"},
            ],
        )
        assert BoilerDevice(d).schedule_status == "active"

    def test_underfloor_thermostat_inheritance(self):
        d = _dto(
            "hvac_underfloor_heating",
            reported=[
                {"key": "main_sensor", "type": "ENUM", "enum_value": "C"},
            ],
        )
        # _ThermostatMixin наследуется
        assert UnderfloorHeatingDevice(d).main_sensor == "C"
