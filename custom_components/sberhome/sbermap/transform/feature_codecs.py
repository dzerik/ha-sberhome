"""Feature codecs — single source of truth для wire↔HA конверсии per feature.

Архитектура (PR #10): каждая Sber-feature имеет свой `FeatureCodec` с парой
методов `to_ha(sber_value)` / `to_sber(ha_value)` + HA-метаданные
(unit_of_measurement, device_class, state_class, suggested_display_precision).

Это устраняет проблему "scaling-формулы рассыпаны по `_transform_*`" — теперь
вся wire-семантика конкретной feature живёт ровно в одном месте.

**Verified wire-семантика** (из decompiled APK + MQTT-SberGate sister project):
- `temperature` (sensor_temp / hvac) → INTEGER × 10 (22.5°C → 225 wire).
- `humidity` → INTEGER 0..100 без scale.
- `air_pressure` → INTEGER hPa без scale.
- `hvac_temp_set` → INTEGER целые градусы (без × 10!).
- `cur_voltage` / `cur_power` → INTEGER без scale (V / W).
- `cur_current` → INTEGER без scale в Amperes (НЕ mA, как раньше думали).
- `light_brightness` → INTEGER в device-range (default 100..900) → HA 0..255.
- `volume_int` → INTEGER 0..100 → HA 0.0..1.0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
)


# ============================================================================
# Codec interface
# ============================================================================
class FeatureCodec(Protocol):
    """Bidirectional wire↔HA конвертер для одной Sber-feature."""

    unit_of_measurement: str | None
    device_class: Any | None
    state_class: Any | None
    entity_category: Any | None
    suggested_display_precision: int | None
    icon: str | None

    def to_ha(self, sber_value: Any) -> Any:
        """Sber wire value → HA-friendly value."""
        ...

    def to_sber(self, ha_value: Any) -> Any:
        """HA value → Sber wire value (reverse)."""
        ...


# ============================================================================
# Concrete codec implementations
# ============================================================================
@dataclass(slots=True, frozen=True)
class IntegerCodec:
    """Просто INTEGER без scale (humidity, voltage, power, и т.п.)."""

    unit_of_measurement: str | None = None
    device_class: Any | None = None
    state_class: Any | None = SensorStateClass.MEASUREMENT
    entity_category: Any | None = None
    suggested_display_precision: int | None = None
    icon: str | None = None

    def to_ha(self, sber_value: Any) -> int | None:
        if sber_value is None:
            return None
        return int(sber_value)

    def to_sber(self, ha_value: Any) -> int | None:
        if ha_value is None:
            return None
        return int(ha_value)


@dataclass(slots=True, frozen=True)
class FloatCodec:
    """FLOAT без scale (для совместимости с float-feature, e.g. при проверке)."""

    unit_of_measurement: str | None = None
    device_class: Any | None = None
    state_class: Any | None = SensorStateClass.MEASUREMENT
    entity_category: Any | None = None
    suggested_display_precision: int | None = None
    icon: str | None = None

    def to_ha(self, sber_value: Any) -> float | None:
        if sber_value is None:
            return None
        return float(sber_value)

    def to_sber(self, ha_value: Any) -> float | None:
        if ha_value is None:
            return None
        return float(ha_value)


@dataclass(slots=True, frozen=True)
class IntegerScaleCodec:
    """INTEGER × scale (e.g. temperature: wire 225 → HA 22.5).

    `scale` — множитель wire→HA. Для temperature scale=0.1 (wire 225 → 22.5).
    Для current (если бы был mA→A) scale=0.001.
    """

    scale: float = 1.0
    unit_of_measurement: str | None = None
    device_class: Any | None = None
    state_class: Any | None = SensorStateClass.MEASUREMENT
    entity_category: Any | None = None
    suggested_display_precision: int | None = None
    icon: str | None = None

    def to_ha(self, sber_value: Any) -> float | None:
        if sber_value is None:
            return None
        return float(sber_value) * self.scale

    def to_sber(self, ha_value: Any) -> int | None:
        if ha_value is None:
            return None
        return int(round(float(ha_value) / self.scale))


@dataclass(slots=True, frozen=True)
class TemperatureCodec:
    """Temperature: wire INTEGER × 10 → HA float Celsius.

    Приходит и как INTEGER (×10), и как FLOAT (legacy/наш-mock-формат).
    Если приходит float (e.g. 22.5) — берём как есть.
    Если int — делим на 10 (225 → 22.5).
    """

    unit_of_measurement: str | None = UnitOfTemperature.CELSIUS
    device_class: Any | None = SensorDeviceClass.TEMPERATURE
    state_class: Any | None = SensorStateClass.MEASUREMENT
    entity_category: Any | None = None
    suggested_display_precision: int | None = 1
    icon: str | None = None

    def to_ha(self, sber_value: Any) -> float | None:
        if sber_value is None:
            return None
        # Если float (наш mock или legacy wire) — берём как есть.
        # Если int (реальный Sber wire) — делим на 10.
        if isinstance(sber_value, bool):
            # bool — частный случай int, но не температура
            return None
        if isinstance(sber_value, float):
            return sber_value
        return float(sber_value) / 10.0

    def to_sber(self, ha_value: Any) -> int | None:
        if ha_value is None:
            return None
        return int(round(float(ha_value) * 10))


@dataclass(slots=True, frozen=True)
class BoolCodec:
    """BOOL — bool one-to-one."""

    device_class: Any | None = None
    entity_category: Any | None = None
    icon: str | None = None
    # Sensor metadata не нужны для бинарных entities, но соответствуют Protocol.
    unit_of_measurement: str | None = None
    state_class: Any | None = None
    suggested_display_precision: int | None = None

    def to_ha(self, sber_value: Any) -> bool | None:
        if sber_value is None:
            return None
        return bool(sber_value)

    def to_sber(self, ha_value: Any) -> bool | None:
        if ha_value is None:
            return None
        return bool(ha_value)


@dataclass(slots=True, frozen=True)
class EnumCodec:
    """ENUM — string passthrough (e.g. light_mode, hvac_work_mode)."""

    device_class: Any | None = None
    entity_category: Any | None = None
    icon: str | None = None
    unit_of_measurement: str | None = None
    state_class: Any | None = None
    suggested_display_precision: int | None = None

    def to_ha(self, sber_value: Any) -> str | None:
        if sber_value is None:
            return None
        return str(sber_value)

    def to_sber(self, ha_value: Any) -> str | None:
        if ha_value is None:
            return None
        return str(ha_value)


@dataclass(slots=True, frozen=True)
class VolumeCodec:
    """volume_int: wire INTEGER 0..100 → HA float 0.0..1.0."""

    unit_of_measurement: str | None = None
    device_class: Any | None = None
    state_class: Any | None = None
    entity_category: Any | None = None
    suggested_display_precision: int | None = None
    icon: str | None = None

    def to_ha(self, sber_value: Any) -> float | None:
        if sber_value is None:
            return None
        return float(sber_value) / 100.0

    def to_sber(self, ha_value: Any) -> int | None:
        if ha_value is None:
            return None
        return int(round(float(ha_value) * 100))


# ============================================================================
# FEATURE CODECS REGISTRY
# Single source of truth — все wire↔HA конверсии для каждой Sber-feature.
# ============================================================================
FEATURE_CODECS: dict[str, FeatureCodec] = {
    # ---- Temperature/humidity/pressure (sensor_temp + climate) ----
    "temperature": TemperatureCodec(),  # CRITICAL: wire INTEGER × 10
    "humidity": IntegerCodec(
        unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        suggested_display_precision=0,
    ),
    "air_pressure": IntegerCodec(
        unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
        suggested_display_precision=0,
    ),

    # ---- Power monitoring (socket / relay) ----
    # NOTE: Sber wire for cur_current — INTEGER в Amperes (не mA, как раньше думали).
    # Подтверждено через MQTT-SberGate sister project + decompiled APK.
    "cur_voltage": IntegerCodec(
        unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        suggested_display_precision=1,
    ),
    "cur_current": IntegerCodec(
        unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=2,
    ),
    "cur_power": IntegerCodec(
        unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        suggested_display_precision=1,
    ),

    # ---- Kettle ----
    "kitchen_water_temperature": IntegerCodec(
        unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=0,
    ),
    "kitchen_water_temperature_set": IntegerCodec(
        unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
    ),
    "kitchen_water_level": IntegerCodec(
        unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
    "kitchen_water_low_level": BoolCodec(
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:water-alert",
    ),

    # ---- HVAC ----
    "hvac_temp_set": IntegerCodec(
        unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=0,
    ),
    "hvac_humidity_set": IntegerCodec(
        unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
    ),
    "hvac_water_level": IntegerCodec(
        unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:water-percent",
    ),
    "hvac_water_percentage": IntegerCodec(
        unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:water",
    ),
    "hvac_water_low_level": BoolCodec(
        device_class=BinarySensorDeviceClass.PROBLEM,
        icon="mdi:water-alert",
    ),
    "hvac_replace_filter": BoolCodec(
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:air-filter",
    ),
    "hvac_replace_ionizator": BoolCodec(
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:flash",
    ),
    "hvac_work_mode": EnumCodec(),
    "hvac_air_flow_power": EnumCodec(),
    "hvac_air_flow_direction": EnumCodec(icon="mdi:air-filter"),
    "hvac_thermostat_mode": EnumCodec(icon="mdi:thermostat"),
    "hvac_heating_rate": EnumCodec(
        entity_category=EntityCategory.CONFIG, icon="mdi:speedometer"
    ),
    "hvac_direction_set": EnumCodec(icon="mdi:arrow-decision"),
    "hvac_night_mode": BoolCodec(
        entity_category=EntityCategory.CONFIG, icon="mdi:weather-night"
    ),
    "hvac_ionization": BoolCodec(
        entity_category=EntityCategory.CONFIG, icon="mdi:flash"
    ),
    "hvac_aromatization": BoolCodec(
        entity_category=EntityCategory.CONFIG, icon="mdi:scent"
    ),
    "hvac_decontaminate": BoolCodec(
        entity_category=EntityCategory.CONFIG, icon="mdi:shield-sun"
    ),

    # ---- Light ----
    # Brightness scaling — through dedicated `lights.py` per-device config
    # (не через FEATURE_CODECS, так как range зависит от device).
    "light_mode": EnumCodec(),
    # light_brightness, light_colour, light_colour_temp — через LightConfig.

    # ---- Cover ----
    "open_set": IntegerCodec(unit_of_measurement=PERCENTAGE),
    "open_percentage": IntegerCodec(
        unit_of_measurement=PERCENTAGE, suggested_display_precision=0
    ),
    "open_state": EnumCodec(),
    "open_rate": EnumCodec(
        entity_category=EntityCategory.CONFIG, icon="mdi:speedometer"
    ),
    "light_transmission_percentage": IntegerCodec(
        unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        icon="mdi:weather-sunny",
    ),

    # ---- Sensors (binary) ----
    "water_leak_state": BoolCodec(device_class=BinarySensorDeviceClass.MOISTURE),
    "doorcontact_state": BoolCodec(device_class=BinarySensorDeviceClass.DOOR),
    "motion_state": BoolCodec(device_class=BinarySensorDeviceClass.MOTION),
    "smoke_state": BoolCodec(device_class=BinarySensorDeviceClass.SMOKE),
    "gas_leak_state": BoolCodec(device_class=BinarySensorDeviceClass.GAS),
    "tamper_alarm": BoolCodec(
        device_class=BinarySensorDeviceClass.TAMPER,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "alarm_mute": BoolCodec(icon="mdi:bell-off"),
    "sensor_sensitive": EnumCodec(entity_category=EntityCategory.CONFIG),
    "temp_unit_view": EnumCodec(entity_category=EntityCategory.CONFIG),

    # ---- Common (battery, signal, online) ----
    "battery_percentage": IntegerCodec(
        unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "signal_strength": IntegerCodec(
        unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "battery_low_power": BoolCodec(
        device_class=BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "online": BoolCodec(device_class=BinarySensorDeviceClass.CONNECTIVITY),

    # ---- Switches ----
    "on_off": BoolCodec(),
    "child_lock": BoolCodec(
        entity_category=EntityCategory.CONFIG, icon="mdi:lock"
    ),

    # ---- TV / Media player ----
    "volume_int": VolumeCodec(),
    "mute": BoolCodec(),
    "source": EnumCodec(),
    "channel_int": IntegerCodec(),
    "direction": EnumCodec(),
    "custom_key": EnumCodec(),

    # ---- Vacuum ----
    "vacuum_cleaner_status": EnumCodec(),  # mapping → VacuumActivity делается отдельно
    "vacuum_cleaner_program": EnumCodec(icon="mdi:robot-vacuum"),
    "vacuum_cleaner_cleaning_type": EnumCodec(icon="mdi:broom"),
    "vacuum_cleaner_command": EnumCodec(),  # write-only

    # ---- Intercom ----
    "incoming_call": BoolCodec(
        device_class=BinarySensorDeviceClass.OCCUPANCY, icon="mdi:phone-ring"
    ),
    "unlock": BoolCodec(icon="mdi:door-open"),  # button
    "reject_call": BoolCodec(icon="mdi:phone-hangup"),  # button

    # ---- Scenario buttons (events) ----
    # button_event/button_1..10_event/button_left/right/top_left/etc — все ENUM.
    "button_event": EnumCodec(),
    **{f"button_{i}_event": EnumCodec() for i in range(1, 11)},
    "button_left_event": EnumCodec(),
    "button_right_event": EnumCodec(),
    "button_top_left_event": EnumCodec(),
    "button_top_right_event": EnumCodec(),
    "button_bottom_left_event": EnumCodec(),
    "button_bottom_right_event": EnumCodec(),

    # ---- LED-strip ----
    "sleep_timer": IntegerCodec(
        unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.CONFIG,
        icon="mdi:timer",
    ),
}


def codec_for(feature: str) -> FeatureCodec | None:
    """Return codec для feature или None если неизвестна."""
    return FEATURE_CODECS.get(feature)


def to_ha(feature: str, sber_value: Any) -> Any:
    """Конверт wire → HA для feature. None если codec неизвестен."""
    codec = FEATURE_CODECS.get(feature)
    if codec is None:
        return sber_value  # passthrough fallback
    return codec.to_ha(sber_value)


def to_sber(feature: str, ha_value: Any) -> Any:
    """Конверт HA → wire для feature. None если codec неизвестен."""
    codec = FEATURE_CODECS.get(feature)
    if codec is None:
        return ha_value  # passthrough fallback
    return codec.to_sber(ha_value)


__all__ = [
    "FEATURE_CODECS",
    "BoolCodec",
    "EnumCodec",
    "FeatureCodec",
    "FloatCodec",
    "IntegerCodec",
    "IntegerScaleCodec",
    "TemperatureCodec",
    "VolumeCodec",
    "codec_for",
    "to_ha",
    "to_sber",
]
