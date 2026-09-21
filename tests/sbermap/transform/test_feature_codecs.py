"""Unit tests for feature_codecs (PR #10).

Покрывает критичные API↔HA конверсии:
- temperature ×10 (CRITICAL)
- voltage/power без скейла, current — миллиамперы → амперы
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
    EnumBoolCodec,
    EnumCodec,
    FloatCodec,
    IntegerCodec,
    IntegerScaleCodec,
    TemperatureCodec,
    VolumeCodec,
    codec_for,
    to_ha,
    to_sber,
)
from custom_components.sberhome.sbermap.transform.feature_specs import FEATURE_SPECS


class TestTemperatureCodec:
    """Temperature API — FLOAT °C, direct pass-through (no ×10 scaling).

    Sber client SDK использует `Float.valueOf(value)` прямо в Celsius
    (см. TemperatureSensorStateConverter). Раньше мы делили на 10 — это
    была ложная гипотеза, приводившая к отображению 24°C как 2.4°C.
    """

    @pytest.fixture
    def codec(self):
        return TemperatureCodec()

    def test_float_wire_passthrough(self, codec):
        # API float 23.9°C → HA 23.9°C
        assert codec.to_ha(23.9) == 23.9

    def test_int_wire_not_divided(self, codec):
        # Если API пришёл int (округлённое значение от Tuya-bridge) — не делим.
        assert codec.to_ha(24) == 24.0

    def test_zero(self, codec):
        assert codec.to_ha(0) == 0.0
        assert codec.to_ha(0.0) == 0.0

    def test_negative_temperature(self, codec):
        assert codec.to_ha(-5.0) == -5.0
        assert codec.to_ha(-40) == -40.0

    def test_bool_ignored(self, codec):
        # bool — частный случай int, но не температура → None
        assert codec.to_ha(True) is None
        assert codec.to_ha(False) is None

    def test_to_sber_passthrough(self, codec):
        assert codec.to_sber(22.5) == 22.5
        assert codec.to_sber(24) == 24.0

    def test_none_passthrough(self, codec):
        assert codec.to_ha(None) is None
        assert codec.to_sber(None) is None

    def test_invalid_input_returns_none(self, codec):
        assert codec.to_ha("not-a-number") is None

    def test_metadata(self, codec):
        assert codec.unit_of_measurement == UnitOfTemperature.CELSIUS
        assert codec.device_class is SensorDeviceClass.TEMPERATURE
        assert codec.suggested_display_precision == 1


class TestPowerMonitoringCodecs:
    """voltage/power — FLOAT, current — INTEGER в мА (per клиентский SDK)."""

    def test_voltage_float_passthrough(self):
        codec = FEATURE_CODECS["cur_voltage"]
        assert codec.to_ha(220.5) == 220.5  # точность сохраняется
        assert codec.to_ha(230) == 230.0
        assert codec.unit_of_measurement == UnitOfElectricPotential.VOLT
        assert codec.device_class is SensorDeviceClass.VOLTAGE

    @pytest.mark.parametrize("key", ["cur_current", "current"])
    def test_current_milliamps_to_amperes(self, key):
        # Sber отдаёт ток в миллиамперах (C2C: «Текущий ток, мА», пример 9000),
        # HA-сенсор — в амперах. Раньше 150 мА показывались как 150 А.
        spec = FEATURE_SPECS[key]
        codec = spec.codec
        assert codec.to_ha(150) == pytest.approx(0.15)
        assert codec.to_ha("9000") == pytest.approx(9.0)
        assert codec.to_ha(0) == 0
        assert codec.to_ha(None) is None
        assert codec.to_ha("low") is None  # не число — без падения опроса
        assert codec.unit_of_measurement == UnitOfElectricCurrent.AMPERE
        assert codec.device_class is SensorDeviceClass.CURRENT
        assert FEATURE_CODECS["cur_current"] is codec

    def test_power_float_passthrough(self):
        codec = FEATURE_CODECS["cur_power"]
        assert codec.to_ha(0.5) == 0.5  # маленькая нагрузка не обнуляется
        assert codec.to_ha(345) == 345.0
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


class TestEnumBoolCodec:
    """ENUM→bool codec для радара присутствия Aura (СберБум 2.0).

    `motion_sensor` приходит как ENUM (no_motion/any_motion/sensor_disabled),
    но HA-сущность — бинарный датчик присутствия. Обычный EnumCodec вернул бы
    непустую строку (даже для "no_motion"), а `STATE_ON if ha_value else …` в
    маппере трактует любую непустую строку как истину → датчик залипал бы в ON.
    EnumBoolCodec явно решает, какие enum-значения считать «присутствие есть».
    """

    def test_only_listed_values_are_true(self):
        codec = EnumBoolCodec(on_values=frozenset({"any_motion"}))
        assert codec.to_ha("any_motion") is True
        assert codec.to_ha("no_motion") is False
        # радар выключен пользователем — присутствия нет (а не «ON»)
        assert codec.to_ha("sensor_disabled") is False
        # неизвестное значение не считается присутствием
        assert codec.to_ha("whatever_new_enum") is False

    def test_missing_value_stays_missing(self):
        codec = EnumBoolCodec(on_values=frozenset({"any_motion"}))
        assert codec.to_ha(None) is None

    def test_read_only_no_write(self):
        # Состояние радара только читается: команды на запись присутствия нет.
        codec = EnumBoolCodec(on_values=frozenset({"any_motion"}))
        assert codec.to_sber(True) is None
        assert codec.to_sber(None) is None

    def test_carries_binary_metadata(self):
        codec = EnumBoolCodec(
            on_values=frozenset({"any_motion"}),
            device_class=BinarySensorDeviceClass.OCCUPANCY,
        )
        assert codec.device_class is BinarySensorDeviceClass.OCCUPANCY


class TestAuraFeatureSpecs:
    """Дескрипторы новых Aura-атрибутов (СберБум 2.0)."""

    def test_motion_sensor_is_occupancy_binary(self):
        """motion_sensor — датчик присутствия (mmWave), device_class=occupancy."""
        codec = FEATURE_SPECS["motion_sensor"].codec
        assert codec.device_class is BinarySensorDeviceClass.OCCUPANCY
        # именно EnumBoolCodec: сырой enum "no_motion" не должен стать ON
        assert codec.to_ha("no_motion") is False
        assert codec.to_ha("any_motion") is True


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
        # API 5500 → HA 55.0
        assert c.to_ha(5500) == 55.0
        # HA 55 → API 5500
        assert c.to_sber(55) == 5500


class TestRegistryCoverage:
    """Smoke: все известные features имеют codec."""

    @pytest.mark.parametrize(
        "feature",
        [
            # Sensors
            "temperature",
            "humidity",
            "air_pressure",
            "battery_percentage",
            "signal_strength",
            "battery_low_power",
            # Power monitoring
            "cur_voltage",
            "cur_current",
            "cur_power",
            # On/off + extras
            "on_off",
            "child_lock",
            "hvac_night_mode",
            "hvac_ionization",
            "hvac_aromatization",
            "hvac_decontaminate",
            "alarm_mute",
            # Light
            "light_mode",
            # Cover
            "open_set",
            "open_percentage",
            "open_state",
            "open_rate",
            "light_transmission_percentage",
            # HVAC
            "hvac_temp_set",
            "hvac_humidity_set",
            "hvac_water_level",
            "hvac_water_percentage",
            "hvac_water_low_level",
            "hvac_replace_filter",
            "hvac_replace_ionizator",
            "hvac_work_mode",
            "hvac_air_flow_power",
            "hvac_air_flow_direction",
            "hvac_thermostat_mode",
            "hvac_heating_rate",
            "hvac_direction_set",
            # Kettle
            "kitchen_water_temperature",
            "kitchen_water_temperature_set",
            "kitchen_water_level",
            "kitchen_water_low_level",
            # Sensors (binary)
            "water_leak_state",
            "doorcontact_state",
            "motion_state",
            "smoke_state",
            "gas_leak_state",
            "tamper_alarm",
            "sensor_sensitive",
            "temp_unit_view",
            # TV
            "volume_int",
            "mute",
            "source",
            "channel_int",
            "direction",
            "custom_key",
            # Vacuum
            "vacuum_cleaner_status",
            "vacuum_cleaner_program",
            "vacuum_cleaner_cleaning_type",
            "vacuum_cleaner_command",
            # Intercom
            "online",
            "incoming_call",
            "unlock",
            "reject_call",
            # Scenario buttons
            "button_event",
            "button_1_event",
            "button_5_event",
            "button_left_event",
            "button_top_left_event",
            # LED-strip
            "sleep_timer",
        ],
    )
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

    def test_to_ha_temperature_passthrough(self):
        assert to_ha("temperature", 22.5) == 22.5
        assert to_ha("temperature", 24) == 24.0

    def test_to_sber_temperature_passthrough(self):
        assert to_sber("temperature", 22.5) == 22.5


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


_ALL_CODECS = [
    IntegerCodec(),
    FloatCodec(),
    IntegerScaleCodec(scale=0.1),
    TemperatureCodec(),
    BoolCodec(),
    EnumCodec(),
    EnumBoolCodec(on_values=frozenset({"any_motion"})),
    VolumeCodec(),
]


class TestCodecContract:
    """Общий контракт всех кодеков: отсутствующее значение остаётся отсутствующим."""

    @pytest.mark.parametrize("codec", _ALL_CODECS, ids=lambda c: type(c).__name__)
    def test_none_in_both_directions(self, codec):
        assert codec.to_ha(None) is None
        assert codec.to_sber(None) is None

    @pytest.mark.parametrize(
        ("codec", "sber", "ha"),
        [
            (IntegerCodec(), 45, 45),
            (FloatCodec(), 0.35, 0.35),
            (IntegerScaleCodec(scale=0.1), 225, 22.5),
            (TemperatureCodec(), 21.5, 21.5),
            (BoolCodec(), True, True),
            (EnumCodec(), "eco", "eco"),
            (VolumeCodec(), 40, 0.4),
        ],
        ids=lambda v: type(v).__name__ if not isinstance(v, (int, float, str)) else str(v),
    )
    def test_round_trip(self, codec, sber, ha):
        assert codec.to_ha(sber) == pytest.approx(ha)
        assert codec.to_sber(ha) == pytest.approx(sber)

    @pytest.mark.parametrize(
        "codec",
        [IntegerCodec(), IntegerScaleCodec(scale=0.001), TemperatureCodec()],
        ids=lambda c: type(c).__name__,
    )
    def test_non_numeric_value_is_dropped_not_raised(self, codec):
        """Устройство прислало ENUM вместо числа — поле пропадает, опрос не падает."""
        assert codec.to_ha("medium") is None
        assert codec.to_sber("medium") is None
