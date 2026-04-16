"""Тесты bidirectional transform (Sber → HA + HA → Sber)."""

from __future__ import annotations

import pytest

from custom_components.sberhome.sbermap import (
    MappingError,
    SberState,
    SberStateBundle,
    SberValue,
    ha_climate_to_sber,
    ha_cover_to_sber,
    ha_light_to_sber,
    ha_switch_to_sber,
    ha_to_sber_generic,
    sber_to_ha,
)
from custom_components.sberhome.sbermap.values import HsvColor


# ====================================================================
# Sber → HA transforms
# ====================================================================
def _bundle(*states):
    return SberStateBundle(device_id="x", states=tuple(states))


class TestSberToHaLight:
    def test_basic_on(self):
        b = _bundle(SberState("on_off", SberValue.of_bool(True)))
        out = sber_to_ha("light", "dev1", "Lamp", b)
        assert len(out) == 1
        assert out[0].platform == "light"
        assert out[0].state == "on"

    def test_brightness_scaled(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("light_brightness", SberValue.of_int(900)),  # max
        )
        out = sber_to_ha("light", "dev1", "Lamp", b)
        # 900 (max raw) → 255 (HA max)
        assert out[0].attributes["brightness"] == 255

    def test_color_attrs(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("light_colour", SberValue.of_color(HsvColor(200, 80, 90))),
        )
        out = sber_to_ha("light", "dev1", "Lamp", b)
        assert out[0].attributes["hs_color"] == (200.0, 80.0)


class TestSberToHaSocket:
    def test_creates_switch_plus_sensors(self):
        # Sber wire: voltage/current/power — INTEGER (V/A/W) без скейла.
        # Подтверждено через MQTT-SberGate sister project.
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("voltage", SberValue.of_int(230)),
            SberState("current", SberValue.of_int(2)),  # A напрямую
            SberState("power", SberValue.of_int(345)),
        )
        out = sber_to_ha("socket", "dev1", "Socket", b)
        platforms = sorted(e.platform for e in out)
        assert platforms == ["sensor", "sensor", "sensor", "switch"]
        cur = next(e for e in out if "Current" in e.name)
        assert cur.state == 2  # raw INTEGER A
        volt = next(e for e in out if "Voltage" in e.name)
        assert volt.state == 230  # raw INTEGER V


class TestSberToHaTempSensor:
    def test_creates_sensors(self):
        b = _bundle(
            SberState("temperature", SberValue.of_float(22.5)),
            SberState("humidity", SberValue.of_int(60)),
            SberState("air_pressure", SberValue.of_int(1013)),
        )
        out = sber_to_ha("sensor_temp", "dev1", "Sensor", b)
        assert len(out) == 3
        assert all(e.platform == "sensor" for e in out)
        device_classes = {e.device_class for e in out}
        assert device_classes == {"temperature", "humidity", "atmospheric_pressure"}


class TestSberToHaBinarySensors:
    @pytest.mark.parametrize("category,key,device_class", [
        ("sensor_water_leak", "water_leak_state", "moisture"),
        ("sensor_door", "doorcontact_state", "door"),
        ("sensor_pir", "motion_state", "motion"),
        ("sensor_smoke", "smoke_state", "smoke"),
        ("sensor_gas", "gas_leak_state", "gas"),
    ])
    def test_creates_binary_sensor(self, category, key, device_class):
        b = _bundle(SberState(key, SberValue.of_bool(True)))
        out = sber_to_ha(category, "d", "S", b)
        assert len(out) == 1
        assert out[0].platform == "binary_sensor"
        assert out[0].device_class == device_class
        assert out[0].state == "on"


class TestSberToHaCover:
    def test_curtain_position_state(self):
        b = _bundle(
            SberState("open_state", SberValue.of_enum("opening")),
            SberState("open_percentage", SberValue.of_int(60)),
        )
        out = sber_to_ha("curtain", "d", "Curtain", b)
        assert out[0].platform == "cover"
        assert out[0].state == "opening"
        assert out[0].attributes["current_position"] == 60
        assert out[0].device_class == "curtain"


class TestSberToHaClimate:
    def test_air_conditioner(self):
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_temp_set", SberValue.of_int(22)),
            SberState("temperature", SberValue.of_float(24.5)),
            SberState("hvac_work_mode", SberValue.of_enum("cool")),
            SberState("hvac_air_flow_power", SberValue.of_enum("high")),
        )
        out = sber_to_ha("hvac_ac", "d", "AC", b)
        assert out[0].platform == "climate"
        assert out[0].state == "cool"
        assert out[0].attributes["temperature"] == 22
        assert out[0].attributes["current_temperature"] == 24.5
        assert out[0].attributes["fan_mode"] == "high"


class TestSberToHaIntercom:
    def test_creates_binary_sensor_plus_buttons(self):
        b = _bundle(SberState("incoming_call", SberValue.of_bool(False)))
        out = sber_to_ha("intercom", "d", "Door", b)
        platforms = sorted(e.platform for e in out)
        assert platforms == ["binary_sensor", "button", "button"]


class TestSberToHaUnknownCategory:
    def test_returns_empty_list(self):
        b = _bundle()
        out = sber_to_ha("brand_new_unknown", "d", "X", b)
        assert out == []


# ====================================================================
# HA → Sber transforms
# ====================================================================
class TestHaLightToSber:
    def test_on_off_only(self):
        b = ha_light_to_sber(device_id="d", is_on=True)
        assert b.value_of("on_off") is True

    def test_brightness_scaled(self):
        b = ha_light_to_sber(device_id="d", is_on=True, brightness=255)
        # HA 255 → Sber 900
        assert b.value_of("light_brightness") == 900

    def test_brightness_zero_clamped_to_min(self):
        b = ha_light_to_sber(device_id="d", is_on=True, brightness=0)
        assert b.value_of("light_brightness") == 100

    def test_hs_color_creates_color_state(self):
        b = ha_light_to_sber(
            device_id="d", is_on=True, brightness=128, hs_color=(180.5, 49.5)
        )
        c = b.value_of("light_colour")
        assert isinstance(c, HsvColor)
        assert c.hue == 180


class TestHaSwitchToSber:
    def test_basic(self):
        b = ha_switch_to_sber(device_id="d", is_on=False)
        assert b.value_of("on_off") is False
        assert len(b.states) == 1


class TestHaClimateToSber:
    def test_full(self):
        b = ha_climate_to_sber(
            device_id="d",
            is_on=True,
            target_temperature=22.0,
            hvac_mode="cool",
            fan_mode="high",
        )
        assert b.value_of("hvac_temp_set") == 22
        assert b.value_of("hvac_work_mode") == "cool"
        assert b.value_of("hvac_air_flow_power") == "high"


class TestHaCoverToSber:
    def test_position(self):
        b = ha_cover_to_sber(device_id="d", position=75)
        assert b.value_of("open_set") == 75

    def test_command_open(self):
        b = ha_cover_to_sber(device_id="d", position=None, command="open")
        assert b.value_of("open_set") == "open"


class TestHaToSberGeneric:
    def test_dispatches_light(self):
        b = ha_to_sber_generic(
            device_id="d", platform="light", state="on", attributes={"brightness": 200}
        )
        assert b.value_of("on_off") is True

    def test_unknown_platform_raises(self):
        with pytest.raises(MappingError):
            ha_to_sber_generic(device_id="d", platform="vacuum", state="on")


# ====================================================================
# Round-trip integration: HA → Sber → wire → Sber → HA
# ====================================================================
class TestRoundTrip:
    def test_light_through_gateway_codec(self):
        from custom_components.sberhome.sbermap import GatewayCodec

        # HA → bundle
        bundle = ha_light_to_sber(
            device_id="d", is_on=True, brightness=200, hs_color=(180, 50)
        )
        # bundle → wire
        codec = GatewayCodec()
        wire = codec.encode_bundle(bundle, direction="desired")
        # wire → bundle (через decode)
        # Используем reported_state ключ для decode_bundle (он принимает оба)
        wire_for_decode = {"reported_state": wire["desired_state"]}
        decoded = codec.decode_bundle(wire_for_decode)
        # decoded → HA entities
        out = sber_to_ha("light", "d", "Lamp", decoded)
        assert out[0].state == "on"
        assert out[0].platform == "light"
        # Brightness round-trip с допуском (scale 100..900 ↔ 0..255)
        assert 195 <= out[0].attributes["brightness"] <= 205


# ====================================================================
# Hybrid HA-deps verification — после PR #15
# Проверяем что transform/ реально использует HA enum'ы (не строки).
# ====================================================================
class TestHybridHaTypes:
    """После migration на HA enum'ы — values должны быть instance HA-types."""

    def test_platform_is_ha_enum(self):
        from homeassistant.const import Platform
        b = _bundle(SberState("on_off", SberValue.of_bool(True)))
        out = sber_to_ha("light", "dev1", "Lamp", b)
        assert isinstance(out[0].platform, Platform)
        assert out[0].platform is Platform.LIGHT

    def test_state_uses_ha_constants(self):
        from homeassistant.const import STATE_OFF, STATE_ON
        b_on = _bundle(SberState("on_off", SberValue.of_bool(True)))
        out = sber_to_ha("light", "dev1", "Lamp", b_on)
        assert out[0].state == STATE_ON

        b_off = _bundle(SberState("on_off", SberValue.of_bool(False)))
        out = sber_to_ha("light", "dev1", "Lamp", b_off)
        assert out[0].state == STATE_OFF

    def test_device_class_is_ha_binary_sensor_enum(self):
        from homeassistant.components.binary_sensor import BinarySensorDeviceClass
        b = _bundle(SberState("water_leak_state", SberValue.of_bool(True)))
        out = sber_to_ha("sensor_water_leak", "d", "S", b)
        assert isinstance(out[0].device_class, BinarySensorDeviceClass)
        assert out[0].device_class is BinarySensorDeviceClass.MOISTURE

    def test_device_class_is_ha_sensor_enum(self):
        from homeassistant.components.sensor import SensorDeviceClass
        b = _bundle(SberState("temperature", SberValue.of_float(22.0)))
        out = sber_to_ha("sensor_temp", "d", "S", b)
        assert isinstance(out[0].device_class, SensorDeviceClass)
        assert out[0].device_class is SensorDeviceClass.TEMPERATURE

    def test_unit_of_measurement_is_ha_constant(self):
        from homeassistant.const import UnitOfTemperature
        b = _bundle(SberState("temperature", SberValue.of_float(20.0)))
        out = sber_to_ha("sensor_temp", "d", "S", b)
        assert out[0].unit_of_measurement == UnitOfTemperature.CELSIUS

    def test_cover_state_uses_ha_cover_state(self):
        from homeassistant.components.cover import CoverState
        b = _bundle(SberState("open_state", SberValue.of_enum("opening")))
        out = sber_to_ha("curtain", "d", "C", b)
        assert out[0].state == CoverState.OPENING

    def test_cover_device_class_is_ha_enum(self):
        from homeassistant.components.cover import CoverDeviceClass
        b = _bundle(SberState("open_state", SberValue.of_enum("closed")))
        out = sber_to_ha("curtain", "d", "C", b)
        assert isinstance(out[0].device_class, CoverDeviceClass)
        assert out[0].device_class is CoverDeviceClass.CURTAIN

    def test_climate_state_uses_hvac_mode_enum(self):
        from homeassistant.components.climate import HVACMode
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("hvac_work_mode", SberValue.of_enum("cool")),
        )
        out = sber_to_ha("hvac_ac", "d", "AC", b)
        assert out[0].state is HVACMode.COOL

    def test_climate_off_state(self):
        from homeassistant.components.climate import HVACMode
        b = _bundle(SberState("on_off", SberValue.of_bool(False)))
        out = sber_to_ha("hvac_ac", "d", "AC", b)
        assert out[0].state is HVACMode.OFF

    def test_brightness_uses_ha_helper(self):
        """value_to_brightness() из HA — точно скейлит 100..900 → 1..255."""
        from homeassistant.util.color import value_to_brightness
        b = _bundle(
            SberState("on_off", SberValue.of_bool(True)),
            SberState("light_brightness", SberValue.of_int(500)),  # midpoint
        )
        out = sber_to_ha("light", "d", "L", b)
        # Reference value через HA helper
        expected = value_to_brightness((100, 900), 500)
        assert out[0].attributes["brightness"] == expected

    def test_ha_to_sber_generic_accepts_platform_enum(self):
        """ha_to_sber_generic принимает Platform enum как и string."""
        from homeassistant.const import Platform
        b1 = ha_to_sber_generic(
            device_id="d", platform=Platform.LIGHT, state="on", attributes={}
        )
        b2 = ha_to_sber_generic(
            device_id="d", platform="light", state="on", attributes={}
        )
        assert b1.value_of("on_off") == b2.value_of("on_off") is True
