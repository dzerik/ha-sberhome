"""Tests for sbermap.transform.sber_to_ha — extras (PR #1).

Покрывает новые transformer'ы:
- common_sensors (battery_percentage, signal_strength)
- common_binary_sensors (battery_low_power)
- extra_switches (child_lock, night_mode, ionization, alarm_mute)
- selects (sensor_sensitive, hvac_thermostat_mode, vacuum_program)
- numbers (kettle target_temperature, led_strip sleep_timer, hvac_ac target_humidity)
- buttons (intercom unlock/reject_call)
- events (scenario_button button_*_event)
- vacuum status mapping
- HVAC mode mapping
"""

from __future__ import annotations

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.climate import HVACMode
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.vacuum import VacuumActivity
from homeassistant.const import EntityCategory, Platform

from custom_components.sberhome.sbermap import (
    SberState,
    SberStateBundle,
    SberValue,
    map_hvac_mode,
    map_hvac_mode_to_sber,
    map_vacuum_status,
    sber_to_ha,
)


def _bundle(*states: SberState, device_id: str = "d1") -> SberStateBundle:
    return SberStateBundle(device_id=device_id, states=tuple(states))


# =============================================================================
# Common sensors (battery, signal_strength)
# =============================================================================
class TestCommonSensors:
    def test_battery_added_for_temp_sensor(self):
        b = _bundle(
            SberState("temperature", SberValue.of_float(22.0)),
            SberState("battery_percentage", SberValue.of_int(85)),
        )
        out = sber_to_ha("sensor_temp", "d", "Sensor", b)
        battery = next(e for e in out if e.unique_id == "d_battery")
        assert battery.platform is Platform.SENSOR
        assert battery.device_class is SensorDeviceClass.BATTERY
        assert battery.state == 85
        assert battery.entity_category is EntityCategory.DIAGNOSTIC

    def test_signal_strength_added_when_present(self):
        b = _bundle(
            SberState("temperature", SberValue.of_float(22.0)),
            SberState("signal_strength", SberValue.of_int(-55)),
        )
        out = sber_to_ha("sensor_temp", "d", "Sensor", b)
        signal = next(e for e in out if e.unique_id == "d_signal_strength")
        assert signal.device_class is SensorDeviceClass.SIGNAL_STRENGTH
        assert signal.state == -55
        assert signal.unit_of_measurement == "dBm"

    def test_no_battery_if_not_in_bundle(self):
        b = _bundle(SberState("temperature", SberValue.of_float(22.0)))
        out = sber_to_ha("sensor_temp", "d", "Sensor", b)
        assert all(e.unique_id != "d_battery" for e in out)


class TestCommonBinarySensors:
    def test_battery_low_added_for_door_sensor(self):
        b = _bundle(
            SberState("doorcontact_state", SberValue.of_bool(False)),
            SberState("battery_low_power", SberValue.of_bool(True)),
        )
        out = sber_to_ha("sensor_door", "d", "Door", b)
        low = next(e for e in out if e.unique_id == "d_battery_low")
        assert low.platform is Platform.BINARY_SENSOR
        assert low.device_class is BinarySensorDeviceClass.BATTERY
        assert low.state == "on"


# =============================================================================
# Extra switches (child_lock, night_mode, ionization, alarm_mute)
# =============================================================================
class TestExtraSwitches:
    def test_socket_creates_child_lock(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("child_lock", SberValue.of_bool(False)),
        )
        out = sber_to_ha("socket", "d", "Plug", b)
        cl = next(e for e in out if e.unique_id == "d_child_lock")
        assert cl.platform is Platform.SWITCH
        assert cl.state == "off"
        assert cl.state_attribute_key == "child_lock"
        assert cl.entity_category is EntityCategory.CONFIG

    def test_hvac_air_purifier_creates_4_extra_switches(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_air_flow_power", SberValue.of_enum("low")),
            SberState("hvac_night_mode", SberValue.of_bool(True)),
            SberState("hvac_ionization", SberValue.of_bool(False)),
            SberState("hvac_aromatization", SberValue.of_bool(False)),
            SberState("hvac_decontaminate", SberValue.of_bool(False)),
        )
        out = sber_to_ha("hvac_air_purifier", "d", "Purifier", b)
        suffixes = {e.state_attribute_key for e in out if e.platform is Platform.SWITCH}
        assert {"hvac_night_mode", "hvac_ionization", "hvac_aromatization", "hvac_decontaminate"} <= suffixes

    def test_alarm_mute_for_smoke_sensor(self):
        b = _bundle(
            SberState("smoke_state", SberValue.of_bool(False)),
            SberState("alarm_mute", SberValue.of_bool(True)),
        )
        out = sber_to_ha("sensor_smoke", "d", "Smoke", b)
        mute = next(e for e in out if e.state_attribute_key == "alarm_mute")
        assert mute.platform is Platform.SWITCH
        assert mute.state == "on"

    def test_extra_switch_skipped_when_not_in_bundle(self):
        """Если фичи нет в bundle — entity не создаётся."""
        b = _bundle(SberState("on_off", SberValue.of_bool(True)))
        out = sber_to_ha("socket", "d", "Plug", b)
        assert all(e.state_attribute_key != "child_lock" for e in out)


# =============================================================================
# Selects (sensor_sensitive, hvac_thermostat_mode, etc.)
# =============================================================================
class TestSelects:
    def test_sensor_sensitive_for_door(self):
        b = _bundle(
            SberState("doorcontact_state", SberValue.of_bool(False)),
            SberState("sensor_sensitive", SberValue.of_enum("auto")),
        )
        out = sber_to_ha("sensor_door", "d", "Door", b)
        sel = next(e for e in out if e.unique_id == "d_sensitivity")
        assert sel.platform is Platform.SELECT
        assert sel.state == "auto"
        assert sel.options == ("auto", "high")

    def test_thermostat_mode_for_boiler(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_thermostat_mode", SberValue.of_enum("eco")),
            SberState("hvac_heating_rate", SberValue.of_enum("medium")),
        )
        out = sber_to_ha("hvac_boiler", "d", "Boiler", b)
        modes = [e for e in out if e.platform is Platform.SELECT]
        keys = {e.state_attribute_key for e in modes}
        assert {"hvac_thermostat_mode", "hvac_heating_rate"} <= keys

    def test_vacuum_program_select(self):
        b = _bundle(
            SberState("vacuum_cleaner_status", SberValue.of_enum("docked")),
            SberState("vacuum_cleaner_program", SberValue.of_enum("smart")),
        )
        out = sber_to_ha("vacuum_cleaner", "d", "V", b)
        prog = next(e for e in out if e.state_attribute_key == "vacuum_cleaner_program")
        assert prog.platform is Platform.SELECT
        assert prog.options == ("perimeter", "spot", "smart")

    def test_select_skipped_when_value_missing(self):
        b = _bundle(SberState("doorcontact_state", SberValue.of_bool(False)))
        out = sber_to_ha("sensor_door", "d", "Door", b)
        assert all(e.platform is not Platform.SELECT for e in out)


# =============================================================================
# Numbers (kettle target_temperature, led_strip sleep_timer, hvac_ac target_humidity)
# =============================================================================
class TestNumbers:
    def test_kettle_target_temperature(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(False)),
            SberState("kitchen_water_temperature_set", SberValue.of_int(80)),
        )
        out = sber_to_ha("kettle", "d", "Kettle", b)
        n = next(e for e in out if e.platform is Platform.NUMBER)
        assert n.state == 80.0
        assert n.min_value == 60
        assert n.max_value == 100
        assert n.step == 10

    def test_hvac_ac_target_humidity(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_humidity_set", SberValue.of_int(55)),
        )
        out = sber_to_ha("hvac_ac", "d", "AC", b)
        n = next(
            e for e in out
            if e.platform is Platform.NUMBER
            and e.state_attribute_key == "hvac_humidity_set"
        )
        assert n.state == 55.0

    def test_window_blind_light_transmission(self):
        b = _bundle(
            SberState("open_percentage", SberValue.of_int(50)),
            SberState("light_transmission_percentage", SberValue.of_int(70)),
        )
        out = sber_to_ha("window_blind", "d", "Blind", b)
        n = next(e for e in out if e.platform is Platform.NUMBER)
        assert n.state == 70.0
        assert n.unit_of_measurement == "%"

    def test_number_skipped_when_value_missing(self):
        b = _bundle(SberState("on_off", SberValue.of_bool(False)))
        out = sber_to_ha("kettle", "d", "Kettle", b)
        assert all(e.platform is not Platform.NUMBER for e in out)


# =============================================================================
# Buttons (intercom)
# =============================================================================
class TestButtons:
    def test_intercom_creates_unlock_and_reject(self):
        b = _bundle(SberState("incoming_call", SberValue.of_bool(True)))
        out = sber_to_ha("intercom", "d", "Intercom", b)
        buttons = [e for e in out if e.platform is Platform.BUTTON]
        suffixes = {e.unique_id for e in buttons}
        assert {"d_unlock", "d_reject_call"} == suffixes

    def test_button_state_attribute_key(self):
        b = _bundle()
        out = sber_to_ha("intercom", "d", "I", b)
        unlock = next(e for e in out if e.unique_id == "d_unlock")
        assert unlock.state_attribute_key == "unlock"


# =============================================================================
# Events (scenario_button)
# =============================================================================
class TestEvents:
    def test_button_1_event_present(self):
        b = _bundle(
            SberState("button_1_event", SberValue.of_enum("click")),
            SberState("button_2_event", SberValue.of_enum("double_click")),
        )
        out = sber_to_ha("scenario_button", "d", "Switch", b)
        assert all(e.platform is Platform.EVENT for e in out)
        assert len(out) == 2
        keys = {e.state_attribute_key for e in out}
        assert keys == {"button_1_event", "button_2_event"}

    def test_event_has_event_types(self):
        b = _bundle(SberState("button_event", SberValue.of_enum("click")))
        out = sber_to_ha("scenario_button", "d", "Btn", b)
        assert out[0].event_types == ("click", "double_click")

    def test_directional_buttons(self):
        b = _bundle(
            SberState("button_left_event", SberValue.of_enum("click")),
            SberState("button_top_right_event", SberValue.of_enum("double_click")),
        )
        out = sber_to_ha("scenario_button", "d", "Cross", b)
        suffixes = {e.unique_id for e in out}
        assert {"d_button_left", "d_button_top_right"} == suffixes


# =============================================================================
# Vacuum status mapping
# =============================================================================
class TestVacuumStatusMap:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("cleaning", VacuumActivity.CLEANING),
            ("running", VacuumActivity.CLEANING),
            ("paused", VacuumActivity.PAUSED),
            ("returning", VacuumActivity.RETURNING),
            ("docked", VacuumActivity.DOCKED),
            ("charging", VacuumActivity.DOCKED),
            ("idle", VacuumActivity.IDLE),
            ("error", VacuumActivity.ERROR),
        ],
    )
    def test_known_status_maps(self, raw, expected):
        assert map_vacuum_status(raw) is expected

    def test_unknown_status_falls_back_to_idle(self):
        assert map_vacuum_status("dancing") is VacuumActivity.IDLE

    def test_none_returns_none(self):
        assert map_vacuum_status(None) is None

    def test_vacuum_transform_uses_mapping(self):
        b = _bundle(
            SberState("vacuum_cleaner_status", SberValue.of_enum("cleaning")),
            SberState("battery_percentage", SberValue.of_int(67)),
        )
        out = sber_to_ha("vacuum_cleaner", "d", "Vac", b)
        primary = next(e for e in out if e.platform is Platform.VACUUM)
        assert primary.state is VacuumActivity.CLEANING
        assert primary.attributes["battery_level"] == 67


# =============================================================================
# HVAC mode mapping
# =============================================================================
class TestHvacModeMapping:
    def test_off_when_not_on(self):
        assert map_hvac_mode("cool", is_on=False) is HVACMode.OFF

    def test_cool_maps(self):
        assert map_hvac_mode("cool", is_on=True) is HVACMode.COOL

    def test_fan_alias(self):
        # И "fan" и "fan_only" → HVACMode.FAN_ONLY
        assert map_hvac_mode("fan", is_on=True) is HVACMode.FAN_ONLY
        assert map_hvac_mode("fan_only", is_on=True) is HVACMode.FAN_ONLY

    def test_unknown_falls_back_to_auto(self):
        assert map_hvac_mode("eco_super", is_on=True) is HVACMode.AUTO

    def test_none_when_on_falls_to_auto(self):
        assert map_hvac_mode(None, is_on=True) is HVACMode.AUTO

    def test_reverse_off_returns_none(self):
        assert map_hvac_mode_to_sber(HVACMode.OFF) is None
        assert map_hvac_mode_to_sber(None) is None

    def test_reverse_cool(self):
        assert map_hvac_mode_to_sber(HVACMode.COOL) == "cool"

    def test_reverse_fan_only(self):
        assert map_hvac_mode_to_sber(HVACMode.FAN_ONLY) == "fan_only"


# =============================================================================
# Sensors (extra: kettle water_temperature, hvac_humidifier water_level)
# =============================================================================
class TestExtraSensors:
    def test_kettle_water_temperature_sensor(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(False)),
            SberState("kitchen_water_temperature", SberValue.of_int(55)),
        )
        out = sber_to_ha("kettle", "d", "K", b)
        s = next(e for e in out if e.unique_id == "d_water_temperature")
        assert s.device_class is SensorDeviceClass.TEMPERATURE
        assert s.state == 55

    def test_hvac_humidifier_water_level(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_water_level", SberValue.of_int(75)),
            SberState("hvac_water_percentage", SberValue.of_int(80)),
        )
        out = sber_to_ha("hvac_humidifier", "d", "H", b)
        suffixes = {e.unique_id for e in out if e.platform is Platform.SENSOR}
        assert {"d_water_level", "d_water_percentage"} <= suffixes


# =============================================================================
# Extra binary sensors (intercom incoming_call, kettle water_low_level)
# =============================================================================
class TestExtraBinarySensors:
    def test_intercom_incoming_call_binary(self):
        b = _bundle(SberState("incoming_call", SberValue.of_bool(True)))
        out = sber_to_ha("intercom", "d", "I", b)
        bs = next(
            e for e in out
            if e.platform is Platform.BINARY_SENSOR
            and e.state_attribute_key == "incoming_call"
        )
        assert bs.state == "on"
        assert bs.device_class is BinarySensorDeviceClass.OCCUPANCY

    def test_kettle_water_low_level(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(False)),
            SberState("kitchen_water_low_level", SberValue.of_bool(True)),
        )
        out = sber_to_ha("kettle", "d", "K", b)
        wl = next(
            e for e in out
            if e.state_attribute_key == "kitchen_water_low_level"
        )
        assert wl.platform is Platform.BINARY_SENSOR
        assert wl.device_class is BinarySensorDeviceClass.PROBLEM
        assert wl.state == "on"

    def test_door_tamper_alarm(self):
        b = _bundle(
            SberState("doorcontact_state", SberValue.of_bool(False)),
            SberState("tamper_alarm", SberValue.of_bool(False)),
        )
        out = sber_to_ha("sensor_door", "d", "Door", b)
        tamper = next(
            e for e in out
            if e.state_attribute_key == "tamper_alarm"
        )
        assert tamper.device_class is BinarySensorDeviceClass.TAMPER
        assert tamper.entity_category is EntityCategory.DIAGNOSTIC


# =============================================================================
# Fan/Humidifier preset_mode_options
# =============================================================================
class TestFanHumidifierOptions:
    def test_hvac_fan_options(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_air_flow_power", SberValue.of_enum("medium")),
        )
        out = sber_to_ha("hvac_fan", "d", "Fan", b)
        primary = next(e for e in out if e.platform is Platform.FAN)
        assert primary.options == ("low", "medium", "high", "turbo")

    def test_hvac_air_purifier_options_include_auto(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_air_flow_power", SberValue.of_enum("auto")),
        )
        out = sber_to_ha("hvac_air_purifier", "d", "AP", b)
        primary = next(e for e in out if e.platform is Platform.FAN)
        assert primary.options == ("auto", "low", "medium", "high", "turbo")

    def test_humidifier_options_and_range(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_humidity_set", SberValue.of_int(55)),
        )
        out = sber_to_ha("hvac_humidifier", "d", "H", b)
        primary = next(e for e in out if e.platform is Platform.HUMIDIFIER)
        assert primary.options == ("auto", "low", "medium", "high", "turbo")
        assert primary.min_value == 30
        assert primary.max_value == 80


# =============================================================================
# Climate adds temperature/humidity sensors
# =============================================================================
class TestClimateAddedSensors:
    def test_hvac_ac_creates_temp_and_humidity_sensors(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("temperature", SberValue.of_float(22.5)),
            SberState("humidity", SberValue.of_int(45)),
        )
        out = sber_to_ha("hvac_ac", "d", "AC", b)
        suffixes = {e.unique_id for e in out if e.platform is Platform.SENSOR}
        assert {"d_temperature", "d_humidity"} <= suffixes

    def test_hvac_heater_temperature_only(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("temperature", SberValue.of_float(21.0)),
        )
        out = sber_to_ha("hvac_heater", "d", "Heat", b)
        suffixes = {e.unique_id for e in out if e.platform is Platform.SENSOR}
        # temperature должна быть, humidity — нет
        assert "d_temperature" in suffixes
        assert "d_humidity" not in suffixes
