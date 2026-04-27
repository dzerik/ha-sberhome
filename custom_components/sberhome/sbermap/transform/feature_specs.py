"""FeatureSpec — единый дескриптор Sber feature → HA entity.

Объединяет API↔HA конверсию (codec) и HA-метаданные (platform, device_class,
unit, icon, etc.) в одном месте. Маппер итерирует по reported_state DeviceDto
и создаёт HaEntityData по дескриптору из FEATURE_SPECS.

Для features, которые являются частью composite primary entity (e.g. on_off
для SWITCH, light_brightness для LIGHT), platform=None — они «consumed»
primary entity и не создают отдельную entity.

Category-specific overrides (e.g. child_lock только для socket/kettle)
задаются через `categories` — frozenset допустимых категорий. None = все.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    Platform,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)

from .feature_codecs import (
    BoolCodec,
    EnumCodec,
    FeatureCodec,
    IntegerCodec,
    TemperatureCodec,
    VolumeCodec,
)


@dataclass(slots=True, frozen=True)
class FeatureSpec:
    """Дескриптор одного Sber feature → HA entity.

    ``platform`` определяет тип HA entity. None означает что feature
    «consumed» primary entity (не создаёт отдельную entity).

    ``categories`` ограничивает, для каких категорий устройств создавать
    entity. None = для всех категорий.
    """

    platform: Platform | None
    codec: FeatureCodec
    entity_category: EntityCategory | None = None
    icon: str | None = None
    # NUMBER-specific
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    # SELECT-specific
    options: tuple[str, ...] | None = None
    # EVENT-specific
    event_types: tuple[str, ...] | None = None
    # BUTTON-specific
    command_value: str | None = None
    # Visibility
    enabled_by_default: bool = True
    # Category restriction (None = all categories)
    categories: frozenset[str] | None = None


def _cats(*names: str) -> frozenset[str]:
    return frozenset(names)


# =============================================================================
# FEATURE_SPECS — single source of truth
# =============================================================================

# Shortcuts
_DIAG = EntityCategory.DIAGNOSTIC
_CFG = EntityCategory.CONFIG
_MEAS = SensorStateClass.MEASUREMENT

FEATURE_SPECS: dict[str, FeatureSpec] = {
    # ---- On/Off (consumed by primary — platform=None) ----
    "on_off": FeatureSpec(platform=None, codec=BoolCodec()),
    "online": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.CONNECTIVITY),
        entity_category=_DIAG,
    ),
    # ---- Sber-speaker / hub diagnostic features ----
    # Ready-флаги под Zigbee/Matter — true когда hub-bridge готов
    # принимать пары новых устройств. У SberBoom Home — это часть
    # подключения хаба к staros, у Sber-портала — Matter controller.
    "zigbee_ready": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(),
        entity_category=_DIAG,
        icon="mdi:zigbee",
        categories=_cats("sber_speaker", "hub"),
    ),
    "matter_ready": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(),
        entity_category=_DIAG,
        icon="mdi:matter",
        categories=_cats("sber_speaker", "hub"),
    ),
    "staros_has_hub": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(),
        entity_category=_DIAG,
        icon="mdi:hubspot",
        categories=_cats("sber_speaker"),
    ),
    "sub_pairing": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(),
        entity_category=_DIAG,
        icon="mdi:link-variant",
        categories=_cats("sber_speaker", "hub"),
    ),
    "detector": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(),
        entity_category=_DIAG,
        icon="mdi:radar",
        categories=_cats("sber_speaker"),
    ),
    # Position enum — стерео-слот колонки (none/left/right) для Sber
    # multi-room audio. Read-write через Sber приложение, мы readonly.
    "position": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        entity_category=_DIAG,
        icon="mdi:speaker-multiple",
        categories=_cats("sber_speaker"),
    ),
    # ---- Common diagnostic sensors (all categories) ----
    "battery_percentage": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.BATTERY,
            entity_category=_DIAG,
        ),
        entity_category=_DIAG,
    ),
    # `signal_strength` приходит как ENUM ("low"/"medium"/"high"), а dBm —
    # в отдельной feature `signal_strength_dbm`. Раньше маппили как INTEGER →
    # `int("low")` валил весь coordinator refresh для устройств где оно
    # enum (все новые `dt_*_m` устройства, например dt_bulb_e27_m).
    "signal_strength": FeatureSpec(
        platform=Platform.SENSOR,
        codec=EnumCodec(entity_category=_DIAG),
        entity_category=_DIAG,
    ),
    "signal_strength_dbm": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement="dBm",
            device_class=SensorDeviceClass.SIGNAL_STRENGTH,
            entity_category=_DIAG,
        ),
        entity_category=_DIAG,
    ),
    "battery_low_power": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.BATTERY),
        entity_category=_DIAG,
    ),
    # ---- Temperature / Humidity / Pressure sensors ----
    "temperature": FeatureSpec(
        platform=Platform.SENSOR,
        codec=TemperatureCodec(),
    ),
    "humidity": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=PERCENTAGE,
            device_class=SensorDeviceClass.HUMIDITY,
        ),
    ),
    "air_pressure": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfPressure.HPA,
            device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        ),
    ),
    # ---- Binary sensors (primary for sensor categories) ----
    "water_leak_state": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.MOISTURE),
    ),
    "doorcontact_state": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.DOOR),
    ),
    "motion_state": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.MOTION),
    ),
    "pir": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.MOTION),
    ),
    "smoke_state": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.SMOKE),
    ),
    "gas_leak_state": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.GAS),
    ),
    "tamper_alarm": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.TAMPER),
        entity_category=_DIAG,
        categories=_cats("sensor_door"),
    ),
    "incoming_call": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.OCCUPANCY),
        icon="mdi:phone-ring",
        categories=_cats("intercom"),
    ),
    # ---- Power monitoring sensors ----
    "cur_voltage": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
        ),
        categories=_cats("socket", "relay"),
    ),
    "voltage": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfElectricPotential.VOLT,
            device_class=SensorDeviceClass.VOLTAGE,
        ),
        categories=_cats("socket", "relay"),
    ),
    "cur_current": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT,
        ),
        categories=_cats("socket", "relay"),
    ),
    "current": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=SensorDeviceClass.CURRENT,
        ),
        categories=_cats("socket", "relay"),
    ),
    "cur_power": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
        ),
        categories=_cats("socket", "relay"),
    ),
    "power": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfPower.WATT,
            device_class=SensorDeviceClass.POWER,
        ),
        categories=_cats("socket", "relay"),
    ),
    # ---- Extra switches (per-category) ----
    "child_lock": FeatureSpec(
        platform=Platform.SWITCH,
        codec=BoolCodec(),
        entity_category=_CFG,
        icon="mdi:lock",
        categories=_cats("socket", "kettle", "vacuum_cleaner"),
    ),
    "alarm_mute": FeatureSpec(
        platform=Platform.SWITCH,
        codec=BoolCodec(),
        entity_category=_CFG,
        icon="mdi:bell-off",
        categories=_cats("sensor_gas", "sensor_smoke"),
    ),
    "hvac_night_mode": FeatureSpec(
        platform=Platform.SWITCH,
        codec=BoolCodec(),
        entity_category=_CFG,
        icon="mdi:weather-night",
        categories=_cats("hvac_ac", "hvac_humidifier", "hvac_air_purifier"),
    ),
    "hvac_ionization": FeatureSpec(
        platform=Platform.SWITCH,
        codec=BoolCodec(),
        entity_category=_CFG,
        icon="mdi:flash",
        categories=_cats("hvac_ac", "hvac_humidifier", "hvac_air_purifier"),
    ),
    "hvac_aromatization": FeatureSpec(
        platform=Platform.SWITCH,
        codec=BoolCodec(),
        entity_category=_CFG,
        icon="mdi:scent",
        categories=_cats("hvac_air_purifier"),
    ),
    "hvac_decontaminate": FeatureSpec(
        platform=Platform.SWITCH,
        codec=BoolCodec(),
        entity_category=_CFG,
        icon="mdi:shield-sun",
        categories=_cats("hvac_air_purifier"),
    ),
    # ---- Extra binary sensors (per-category) ----
    "kitchen_water_low_level": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.PROBLEM),
        icon="mdi:water-alert",
        categories=_cats("kettle"),
    ),
    "hvac_water_low_level": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.PROBLEM),
        icon="mdi:water-alert",
        categories=_cats("hvac_humidifier"),
    ),
    "hvac_replace_filter": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.PROBLEM),
        entity_category=_DIAG,
        icon="mdi:air-filter",
        categories=_cats("hvac_humidifier", "hvac_air_purifier"),
    ),
    "hvac_replace_ionizator": FeatureSpec(
        platform=Platform.BINARY_SENSOR,
        codec=BoolCodec(device_class=BinarySensorDeviceClass.PROBLEM),
        entity_category=_DIAG,
        icon="mdi:flash",
        categories=_cats("hvac_humidifier", "hvac_air_purifier"),
    ),
    # ---- Selects ----
    "open_rate": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("auto", "low", "high"),
        icon="mdi:speedometer",
        entity_category=_CFG,
        categories=_cats("curtain", "gate", "window_blind"),
    ),
    "hvac_air_flow_direction": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("auto", "top", "middle", "bottom"),
        icon="mdi:air-filter",
        categories=_cats("hvac_ac"),
    ),
    "sensor_sensitive": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("auto", "high"),
        entity_category=_CFG,
        categories=_cats("sensor_temp", "sensor_door", "sensor_pir", "sensor_gas"),
    ),
    "temp_unit_view": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("celsius", "fahrenheit"),
        entity_category=_CFG,
        categories=_cats("sensor_temp"),
    ),
    "vacuum_cleaner_program": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("perimeter", "spot", "smart"),
        icon="mdi:robot-vacuum",
        categories=_cats("vacuum_cleaner"),
    ),
    "vacuum_cleaner_cleaning_type": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("dry", "wet", "mixed"),
        icon="mdi:broom",
        categories=_cats("vacuum_cleaner"),
    ),
    "hvac_thermostat_mode": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("auto", "eco", "comfort", "boost"),
        icon="mdi:thermostat",
        categories=_cats("hvac_heater", "hvac_boiler", "hvac_underfloor_heating"),
    ),
    "hvac_heating_rate": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("slow", "medium", "fast"),
        icon="mdi:speedometer",
        entity_category=_CFG,
        categories=_cats("hvac_boiler", "hvac_underfloor_heating"),
    ),
    "hvac_direction_set": FeatureSpec(
        platform=Platform.SELECT,
        codec=EnumCodec(),
        options=("auto", "top", "middle", "bottom", "swing"),
        icon="mdi:arrow-decision",
        categories=_cats("hvac_fan"),
    ),
    # ---- Numbers ----
    "kitchen_water_temperature_set": FeatureSpec(
        platform=Platform.NUMBER,
        codec=IntegerCodec(unit_of_measurement=UnitOfTemperature.CELSIUS),
        min_value=60,
        max_value=100,
        step=10,
        icon="mdi:thermometer",
        categories=_cats("kettle"),
    ),
    "sleep_timer": FeatureSpec(
        platform=Platform.NUMBER,
        codec=IntegerCodec(unit_of_measurement=UnitOfTime.MINUTES),
        min_value=0,
        max_value=720,
        step=1,
        icon="mdi:timer",
        entity_category=_CFG,
        categories=_cats("led_strip"),
    ),
    "hvac_humidity_set": FeatureSpec(
        platform=Platform.NUMBER,
        codec=IntegerCodec(unit_of_measurement=PERCENTAGE),
        min_value=30,
        max_value=80,
        step=5,
        icon="mdi:water-percent",
        categories=_cats("hvac_ac"),
    ),
    "light_transmission_percentage": FeatureSpec(
        platform=Platform.NUMBER,
        codec=IntegerCodec(unit_of_measurement=PERCENTAGE),
        min_value=0,
        max_value=100,
        step=1,
        icon="mdi:weather-sunny",
        categories=_cats("window_blind"),
    ),
    # ---- Extra sensors (per-category) ----
    "kitchen_water_temperature": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(
            unit_of_measurement=UnitOfTemperature.CELSIUS,
            device_class=SensorDeviceClass.TEMPERATURE,
            suggested_display_precision=0,
        ),
        categories=_cats("kettle"),
    ),
    "kitchen_water_level": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(unit_of_measurement=PERCENTAGE, suggested_display_precision=0),
        categories=_cats("kettle"),
    ),
    "hvac_water_level": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(unit_of_measurement=PERCENTAGE, suggested_display_precision=0),
        icon="mdi:water-percent",
        categories=_cats("hvac_humidifier"),
    ),
    "hvac_water_percentage": FeatureSpec(
        platform=Platform.SENSOR,
        codec=IntegerCodec(unit_of_measurement=PERCENTAGE, suggested_display_precision=0),
        icon="mdi:water",
        categories=_cats("hvac_humidifier"),
    ),
    # ---- Buttons ----
    "unlock": FeatureSpec(
        platform=Platform.BUTTON,
        codec=BoolCodec(),
        icon="mdi:door-open",
        categories=_cats("intercom"),
    ),
    "reject_call": FeatureSpec(
        platform=Platform.BUTTON,
        codec=BoolCodec(),
        icon="mdi:phone-hangup",
        categories=_cats("intercom"),
    ),
    # ---- Events (scenario buttons) ----
    "button_event": FeatureSpec(
        platform=Platform.EVENT,
        codec=EnumCodec(),
        event_types=("click", "double_click", "long_press"),
        categories=_cats("scenario_button"),
    ),
    **{
        f"button_{i}_event": FeatureSpec(
            platform=Platform.EVENT,
            codec=EnumCodec(),
            event_types=("click", "double_click", "long_press"),
            categories=_cats("scenario_button"),
        )
        for i in range(1, 11)
    },
    **{
        f"button_{pos}_event": FeatureSpec(
            platform=Platform.EVENT,
            codec=EnumCodec(),
            event_types=("click", "double_click", "long_press"),
            categories=_cats("scenario_button"),
        )
        for pos in ("left", "right", "top_left", "top_right", "bottom_left", "bottom_right")
    },
    # ---- Features consumed by primary (platform=None) — for completeness ----
    "light_brightness": FeatureSpec(platform=None, codec=IntegerCodec()),
    "light_colour": FeatureSpec(platform=None, codec=EnumCodec()),
    "light_colour_temp": FeatureSpec(platform=None, codec=IntegerCodec()),
    "light_mode": FeatureSpec(platform=None, codec=EnumCodec()),
    "hvac_temp_set": FeatureSpec(platform=None, codec=IntegerCodec()),
    "hvac_work_mode": FeatureSpec(platform=None, codec=EnumCodec()),
    "hvac_air_flow_power": FeatureSpec(platform=None, codec=EnumCodec()),
    "open_set": FeatureSpec(platform=None, codec=IntegerCodec()),
    "open_state": FeatureSpec(platform=None, codec=EnumCodec()),
    "open_percentage": FeatureSpec(platform=None, codec=IntegerCodec()),
    "vacuum_cleaner_status": FeatureSpec(platform=None, codec=EnumCodec()),
    "vacuum_cleaner_command": FeatureSpec(platform=None, codec=EnumCodec()),
    "volume_int": FeatureSpec(platform=None, codec=VolumeCodec()),
    "mute": FeatureSpec(platform=None, codec=BoolCodec()),
    "source": FeatureSpec(platform=None, codec=EnumCodec()),
    "channel_int": FeatureSpec(platform=None, codec=IntegerCodec()),
}


def feature_spec_for(key: str) -> FeatureSpec | None:
    """Return FeatureSpec для feature key или None."""
    return FEATURE_SPECS.get(key)


def is_applicable(spec: FeatureSpec, category: str) -> bool:
    """Check if spec applies to given category."""
    return spec.categories is None or category in spec.categories


__all__ = [
    "FEATURE_SPECS",
    "FeatureSpec",
    "feature_spec_for",
    "is_applicable",
]
