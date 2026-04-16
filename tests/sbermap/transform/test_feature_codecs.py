"""Unit tests for feature_codecs (PR #10).

Покрывает критичные wire↔HA конверсии:
- temperature ×10 (CRITICAL)
- voltage/current/power без скейла
- humidity/air_pressure
- volume_int 0..100 → 0.0..1.0
- bool/enum passthrough
- registry coverage (все features из существующих transformers)
"""

from __future__ import annotations

import pytest
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
)

from custom_components.sberhome.sbermap.transform.feature_codecs import (
    FEATURE_CODECS,
    BoolCodec,
    EnumCodec,
    IntegerCodec,
    IntegerScaleCodec,
    TemperatureCodec,
    VolumeCodec,
    codec_for,
    to_ha,
    to_sber,
)


class TestTemperatureCodec:
    """CRITICAL: temperature wire — INTEGER × 10."""

    @pytest.fixture
    def codec(self):
        return TemperatureCodec()

    def test_integer_wire_divided_by_10(self, codec):
        # Sber 225 → HA 22.5°C
        assert codec.to_ha(225) == 22.5

    def test_integer_zero(self, codec):
        assert codec.to_ha(0) == 0.0

    def test_negative_temperature(self, codec):
        # -5.0°C → wire -50
        assert codec.to_ha(-50) == -5.0

    def test_float_wire_passthrough(self, codec):
        # Legacy/наш-mock-формат: float → как есть.
        assert codec.to_ha(22.5) == 22.5

    def test_to_sber_multiplies_by_10(self, codec):
        # HA 22.5°C → wire 225
        assert codec.to_sber(22.5) == 225

    def test_to_sber_rounds(self, codec):
        # HA 22.55 → wire round(225.5) = 226
        assert codec.to_sber(22.55) == 226

    def test_none_passthrough(self, codec):
        assert codec.to_ha(None) is None
        assert codec.to_sber(None) is None

    def test_metadata(self, codec):
        assert codec.unit_of_measurement == UnitOfTemperature.CELSIUS
        assert codec.device_class is SensorDeviceClass.TEMPERATURE
        assert codec.suggested_display_precision == 1


class TestPowerMonitoringCodecs:
    """voltage / current / power — INTEGER без скейла."""

    def test_voltage(self):
        codec = FEATURE_CODECS["cur_voltage"]
        assert codec.to_ha(230) == 230
        assert codec.unit_of_measurement == UnitOfElectricPotential.VOLT
        assert codec.device_class is SensorDeviceClass.VOLTAGE

    def test_current_no_scale(self):
        # Sber wire INTEGER в Amperes напрямую (НЕ mA).
        codec = FEATURE_CODECS["cur_current"]
        assert codec.to_ha(2) == 2
        assert codec.to_ha(15) == 15  # Не делим на 1000!
        assert codec.unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert codec.device_class is SensorDeviceClass.CURRENT

    def test_power(self):
        codec = FEATURE_CODECS["cur_power"]
        assert codec.to_ha(345) == 345
        assert codec.unit_of_measurement == UnitOfPower.WATT
        assert codec.device_class is SensorDeviceClass.POWER


class TestHumidityPressure:
    def test_humidity(self):
        codec = FEATURE_CODECS["humidity"]
        assert codec.to_ha(45) == 45
        assert codec.unit_of_measurement == PERCENTAGE
        assert codec.device_class is SensorDeviceClass.HUMIDITY

    def test_air_pressure(self):
        codec = FEATURE_CODECS["air_pressure"]
        assert codec.to_ha(1013) == 1013
        assert codec.unit_of_measurement == UnitOfPressure.HPA
        assert codec.device_class is SensorDeviceClass.ATMOSPHERIC_PRESSURE


class TestVolumeCodec:
    def test_volume_to_ha_scaled_to_1(self):
        codec = VolumeCodec()
        assert codec.to_ha(50) == 0.5
        assert codec.to_ha(100) == 1.0
        assert codec.to_ha(0) == 0.0

    def test_volume_to_sber_scaled_to_100(self):
        codec = VolumeCodec()
        assert codec.to_sber(0.75) == 75
        assert codec.to_sber(1.0) == 100


class TestBoolEnumCodecs:
    def test_bool_passthrough(self):
        codec = BoolCodec()
        assert codec.to_ha(True) is True
        assert codec.to_ha(False) is False

    def test_bool_to_sber(self):
        codec = BoolCodec()
        assert codec.to_sber(True) is True
        assert codec.to_sber(False) is False

    def test_enum_passthrough(self):
        codec = EnumCodec()
        assert codec.to_ha("auto") == "auto"
        assert codec.to_sber("cool") == "cool"


class TestIntegerCodecs:
    def test_integer_basic(self):
        c = IntegerCodec()
        assert c.to_ha(42) == 42

    def test_integer_scale_x100(self):
        c = IntegerScaleCodec(scale=0.01)
        # wire 5500 → HA 55.0
        assert c.to_ha(5500) == 55.0
        # HA 55 → wire 5500
        assert c.to_sber(55) == 5500


class TestRegistryCoverage:
    """Smoke: все известные features имеют codec."""

    @pytest.mark.parametrize("feature", [
        # Sensors
        "temperature", "humidity", "air_pressure",
        "battery_percentage", "signal_strength", "battery_low_power",
        # Power monitoring
        "cur_voltage", "cur_current", "cur_power",
        # On/off + extras
        "on_off", "child_lock",
        "hvac_night_mode", "hvac_ionization",
        "hvac_aromatization", "hvac_decontaminate",
        "alarm_mute",
        # Light
        "light_mode",
        # Cover
        "open_set", "open_percentage", "open_state", "open_rate",
        "light_transmission_percentage",
        # HVAC
        "hvac_temp_set", "hvac_humidity_set",
        "hvac_water_level", "hvac_water_percentage", "hvac_water_low_level",
        "hvac_replace_filter", "hvac_replace_ionizator",
        "hvac_work_mode", "hvac_air_flow_power", "hvac_air_flow_direction",
        "hvac_thermostat_mode", "hvac_heating_rate", "hvac_direction_set",
        # Kettle
        "kitchen_water_temperature", "kitchen_water_temperature_set",
        "kitchen_water_level", "kitchen_water_low_level",
        # Sensors (binary)
        "water_leak_state", "doorcontact_state", "motion_state",
        "smoke_state", "gas_leak_state", "tamper_alarm",
        "sensor_sensitive", "temp_unit_view",
        # TV
        "volume_int", "mute", "source", "channel_int",
        "direction", "custom_key",
        # Vacuum
        "vacuum_cleaner_status", "vacuum_cleaner_program",
        "vacuum_cleaner_cleaning_type", "vacuum_cleaner_command",
        # Intercom
        "online", "incoming_call", "unlock", "reject_call",
        # Scenario buttons
        "button_event", "button_1_event", "button_5_event",
        "button_left_event", "button_top_left_event",
        # LED-strip
        "sleep_timer",
    ])
    def test_feature_has_codec(self, feature):
        assert codec_for(feature) is not None

    def test_unknown_feature_returns_none(self):
        assert codec_for("totally_made_up_feature_xyz") is None


class TestModuleHelpers:
    def test_to_ha_passthrough_for_unknown(self):
        # Unknown feature → passthrough.
        assert to_ha("alien_feature", "x") == "x"

    def test_to_sber_passthrough_for_unknown(self):
        assert to_sber("alien_feature", 42) == 42

    def test_to_ha_temperature_uses_scale(self):
        assert to_ha("temperature", 225) == 22.5

    def test_to_sber_temperature_uses_scale(self):
        assert to_sber("temperature", 22.5) == 225


class TestSpecificMetadata:
    """Точечные проверки device_class/icon."""

    def test_battery_diagnostic(self):
        from homeassistant.const import EntityCategory
        assert FEATURE_CODECS["battery_percentage"].entity_category is EntityCategory.DIAGNOSTIC
        assert FEATURE_CODECS["battery_low_power"].entity_category is EntityCategory.DIAGNOSTIC

    def test_water_leak_moisture(self):
        assert FEATURE_CODECS["water_leak_state"].device_class is BinarySensorDeviceClass.MOISTURE

    def test_motion_sensor(self):
        assert FEATURE_CODECS["motion_state"].device_class is BinarySensorDeviceClass.MOTION

    def test_online_connectivity(self):
        assert FEATURE_CODECS["online"].device_class is BinarySensorDeviceClass.CONNECTIVITY

    def test_child_lock_icon(self):
        assert FEATURE_CODECS["child_lock"].icon == "mdi:lock"

    def test_kitchen_water_temperature_no_scale(self):
        # kettle temperature НЕ ×10 (целые градусы).
        codec = FEATURE_CODECS["kitchen_water_temperature"]
        assert codec.to_ha(85) == 85  # 85°C напрямую
