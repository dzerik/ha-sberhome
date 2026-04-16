"""Sber → HA transform.

Превращает `SberStateBundle` (полученный из codec.decode_bundle()) в список
`HaEntityData` (одна или несколько HA-entity для одного Sber-устройства).

Гибридный режим: использует HA enum'ы (`Platform`, `*DeviceClass`, `STATE_*`,
`HVACMode`, `CoverState`, `UnitOf*`) для type safety. Brightness/units scaling
через стандартные HA-helpers.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.cover import CoverDeviceClass, CoverState
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.vacuum import VacuumActivity
from homeassistant.const import (
    PERCENTAGE,
    STATE_OFF,
    STATE_ON,
    EntityCategory,
    Platform,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.util.color import brightness_to_value, value_to_brightness

from ..values import HsvColor, SberStateBundle
from ._types import HaEntityData
from .feature_codecs import FEATURE_CODECS

# Sber light_brightness 100..900 — диапазон для HA value_to_brightness().
_SBER_BRIGHTNESS_RANGE = (100, 900)


# =============================================================================
# Spec-таблицы (single source of truth, перенос из registry.py)
# =============================================================================


@dataclass(slots=True, frozen=True)
class _ExtraSwitchSpec:
    """Дополнительный switch у сложного устройства (child_lock, night_mode)."""

    key: str
    suffix: str
    icon: str | None = None
    entity_category: EntityCategory | None = EntityCategory.CONFIG


@dataclass(slots=True, frozen=True)
class _SelectSpec:
    key: str
    suffix: str
    options: tuple[str, ...]
    icon: str | None = None
    entity_category: EntityCategory | None = None


@dataclass(slots=True, frozen=True)
class _NumberSpec:
    key: str
    suffix: str
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    icon: str | None = None
    entity_category: EntityCategory | None = None
    scale: float = 1.0


@dataclass(slots=True, frozen=True)
class _ButtonSpec:
    key: str
    suffix: str
    icon: str | None = None
    command_value: str | None = None


@dataclass(slots=True, frozen=True)
class _EventSpec:
    key: str
    suffix: str
    event_types: tuple[str, ...] = ("click", "double_click")


@dataclass(slots=True, frozen=True)
class _ExtraBinarySpec:
    key: str
    suffix: str
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None


@dataclass(slots=True, frozen=True)
class _ExtraSensorSpec:
    key: str
    suffix: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    entity_category: EntityCategory | None = None
    icon: str | None = None
    scale: float = 1.0
    as_int: bool = False
    suggested_display_precision: int | None = None


_CATEGORY_EXTRA_SWITCHES: dict[str, tuple[_ExtraSwitchSpec, ...]] = {
    "socket": (_ExtraSwitchSpec("child_lock", "child_lock", icon="mdi:lock"),),
    "kettle": (_ExtraSwitchSpec("child_lock", "child_lock", icon="mdi:lock"),),
    "vacuum_cleaner": (
        _ExtraSwitchSpec("child_lock", "child_lock", icon="mdi:lock"),
    ),
    "hvac_ac": (
        _ExtraSwitchSpec("hvac_night_mode", "night_mode", icon="mdi:weather-night"),
        _ExtraSwitchSpec("hvac_ionization", "ionization", icon="mdi:flash"),
    ),
    "hvac_humidifier": (
        _ExtraSwitchSpec("hvac_night_mode", "night_mode", icon="mdi:weather-night"),
        _ExtraSwitchSpec("hvac_ionization", "ionization", icon="mdi:flash"),
    ),
    "hvac_air_purifier": (
        _ExtraSwitchSpec("hvac_night_mode", "night_mode", icon="mdi:weather-night"),
        _ExtraSwitchSpec("hvac_ionization", "ionization", icon="mdi:flash"),
        _ExtraSwitchSpec("hvac_aromatization", "aromatization", icon="mdi:scent"),
        _ExtraSwitchSpec("hvac_decontaminate", "decontaminate", icon="mdi:shield-sun"),
    ),
    "sensor_gas": (_ExtraSwitchSpec("alarm_mute", "alarm_mute", icon="mdi:bell-off"),),
    "sensor_smoke": (
        _ExtraSwitchSpec("alarm_mute", "alarm_mute", icon="mdi:bell-off"),
    ),
}


_CATEGORY_SELECTS: dict[str, tuple[_SelectSpec, ...]] = {
    "curtain": (
        _SelectSpec(
            "open_rate", "open_rate", ("auto", "low", "high"),
            icon="mdi:speedometer", entity_category=EntityCategory.CONFIG,
        ),
    ),
    "gate": (
        _SelectSpec(
            "open_rate", "open_rate", ("auto", "low", "high"),
            icon="mdi:speedometer", entity_category=EntityCategory.CONFIG,
        ),
    ),
    "window_blind": (
        _SelectSpec(
            "open_rate", "open_rate", ("auto", "low", "high"),
            icon="mdi:speedometer", entity_category=EntityCategory.CONFIG,
        ),
    ),
    "hvac_ac": (
        _SelectSpec(
            "hvac_air_flow_direction", "air_flow_direction",
            ("auto", "top", "middle", "bottom"), icon="mdi:air-filter",
        ),
    ),
    "sensor_temp": (
        _SelectSpec(
            "sensor_sensitive", "sensitivity", ("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
        _SelectSpec(
            "temp_unit_view", "temp_unit", ("celsius", "fahrenheit"),
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    "sensor_door": (
        _SelectSpec(
            "sensor_sensitive", "sensitivity", ("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    "sensor_pir": (
        _SelectSpec(
            "sensor_sensitive", "sensitivity", ("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    "sensor_gas": (
        _SelectSpec(
            "sensor_sensitive", "sensitivity", ("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    "vacuum_cleaner": (
        _SelectSpec(
            "vacuum_cleaner_program", "program",
            ("perimeter", "spot", "smart"), icon="mdi:robot-vacuum",
        ),
        _SelectSpec(
            "vacuum_cleaner_cleaning_type", "cleaning_type",
            ("dry", "wet", "mixed"), icon="mdi:broom",
        ),
    ),
    "hvac_heater": (
        _SelectSpec(
            "hvac_thermostat_mode", "thermostat_mode",
            ("auto", "eco", "comfort", "boost"), icon="mdi:thermostat",
        ),
    ),
    "hvac_boiler": (
        _SelectSpec(
            "hvac_thermostat_mode", "thermostat_mode",
            ("auto", "eco", "comfort", "boost"), icon="mdi:thermostat",
        ),
        _SelectSpec(
            "hvac_heating_rate", "heating_rate",
            ("slow", "medium", "fast"), icon="mdi:speedometer",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    "hvac_underfloor_heating": (
        _SelectSpec(
            "hvac_thermostat_mode", "thermostat_mode",
            ("auto", "eco", "comfort", "boost"), icon="mdi:thermostat",
        ),
        _SelectSpec(
            "hvac_heating_rate", "heating_rate",
            ("slow", "medium", "fast"), icon="mdi:speedometer",
            entity_category=EntityCategory.CONFIG,
        ),
    ),
    "hvac_fan": (
        _SelectSpec(
            "hvac_direction_set", "direction",
            ("auto", "top", "middle", "bottom", "swing"), icon="mdi:arrow-decision",
        ),
    ),
}


_CATEGORY_NUMBERS: dict[str, tuple[_NumberSpec, ...]] = {
    "kettle": (
        _NumberSpec(
            "kitchen_water_temperature_set", "target_temperature",
            unit=UnitOfTemperature.CELSIUS, min_value=60, max_value=100, step=10,
            icon="mdi:thermometer",
        ),
    ),
    "led_strip": (
        _NumberSpec(
            "sleep_timer", "sleep_timer", unit=UnitOfTime.MINUTES,
            min_value=0, max_value=720, step=1,
            icon="mdi:timer", entity_category=EntityCategory.CONFIG,
        ),
    ),
    "hvac_ac": (
        _NumberSpec(
            "hvac_humidity_set", "target_humidity", unit=PERCENTAGE,
            min_value=30, max_value=80, step=5, icon="mdi:water-percent",
        ),
    ),
    "window_blind": (
        _NumberSpec(
            "light_transmission_percentage", "light_transmission", unit=PERCENTAGE,
            min_value=0, max_value=100, step=1, icon="mdi:weather-sunny",
        ),
    ),
}


_CATEGORY_BUTTONS: dict[str, tuple[_ButtonSpec, ...]] = {
    "intercom": (
        _ButtonSpec("unlock", "unlock", icon="mdi:door-open"),
        _ButtonSpec("reject_call", "reject_call", icon="mdi:phone-hangup"),
    ),
}


# Scenario-button events (одна категория, до 16 кнопок)
_CATEGORY_EVENTS: dict[str, tuple[_EventSpec, ...]] = {
    "scenario_button": (
        _EventSpec("button_event", "button"),
        *(_EventSpec(f"button_{i}_event", f"button_{i}") for i in range(1, 11)),
        _EventSpec("button_left_event", "button_left"),
        _EventSpec("button_right_event", "button_right"),
        _EventSpec("button_top_left_event", "button_top_left"),
        _EventSpec("button_top_right_event", "button_top_right"),
        _EventSpec("button_bottom_left_event", "button_bottom_left"),
        _EventSpec("button_bottom_right_event", "button_bottom_right"),
    ),
}


# Дополнительные binary_sensors сверх primary (e.g. kettle water_low, intercom call)
_CATEGORY_EXTRA_BINARY_SENSORS: dict[str, tuple[_ExtraBinarySpec, ...]] = {
    "sensor_door": (
        _ExtraBinarySpec(
            "tamper_alarm", "tamper", BinarySensorDeviceClass.TAMPER,
            entity_category=EntityCategory.DIAGNOSTIC,
        ),
    ),
    "kettle": (
        _ExtraBinarySpec(
            "kitchen_water_low_level", "water_low_level",
            BinarySensorDeviceClass.PROBLEM, icon="mdi:water-alert",
        ),
    ),
    "hvac_humidifier": (
        _ExtraBinarySpec(
            "hvac_water_low_level", "water_low_level",
            BinarySensorDeviceClass.PROBLEM, icon="mdi:water-alert",
        ),
        _ExtraBinarySpec(
            "hvac_replace_filter", "replace_filter",
            BinarySensorDeviceClass.PROBLEM, EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
        ),
        _ExtraBinarySpec(
            "hvac_replace_ionizator", "replace_ionizator",
            BinarySensorDeviceClass.PROBLEM, EntityCategory.DIAGNOSTIC,
            icon="mdi:flash",
        ),
    ),
    "hvac_air_purifier": (
        _ExtraBinarySpec(
            "hvac_replace_filter", "replace_filter",
            BinarySensorDeviceClass.PROBLEM, EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
        ),
        _ExtraBinarySpec(
            "hvac_replace_ionizator", "replace_ionizator",
            BinarySensorDeviceClass.PROBLEM, EntityCategory.DIAGNOSTIC,
            icon="mdi:flash",
        ),
    ),
    "intercom": (
        _ExtraBinarySpec(
            "incoming_call", "incoming_call",
            BinarySensorDeviceClass.OCCUPANCY, icon="mdi:phone-ring",
        ),
    ),
}


# Common sensors — battery, signal — добавляются ко ВСЕМ категориям если значение есть
_COMMON_SENSORS: tuple[_ExtraSensorSpec, ...] = (
    _ExtraSensorSpec(
        "battery_percentage", "battery",
        SensorDeviceClass.BATTERY, PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC, as_int=True,
    ),
    _ExtraSensorSpec(
        "signal_strength", "signal_strength",
        SensorDeviceClass.SIGNAL_STRENGTH, "dBm",
        entity_category=EntityCategory.DIAGNOSTIC, as_int=True,
    ),
)

# Common binary sensors (battery_low_power)
_COMMON_BINARY_SENSORS: tuple[_ExtraBinarySpec, ...] = (
    _ExtraBinarySpec(
        "battery_low_power", "battery_low",
        BinarySensorDeviceClass.BATTERY,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


# Дополнительные специфические сенсоры на категорию (не common)
_CATEGORY_EXTRA_SENSORS: dict[str, tuple[_ExtraSensorSpec, ...]] = {
    "kettle": (
        _ExtraSensorSpec(
            "kitchen_water_temperature", "water_temperature",
            SensorDeviceClass.TEMPERATURE, UnitOfTemperature.CELSIUS,
            suggested_display_precision=0,
        ),
        _ExtraSensorSpec(
            "kitchen_water_level", "water_level", unit=PERCENTAGE,
            suggested_display_precision=0,
        ),
    ),
    "hvac_humidifier": (
        _ExtraSensorSpec(
            "hvac_water_level", "water_level", unit=PERCENTAGE,
            suggested_display_precision=0, icon="mdi:water-percent",
        ),
        _ExtraSensorSpec(
            "hvac_water_percentage", "water_percentage", unit=PERCENTAGE,
            suggested_display_precision=0, icon="mdi:water",
        ),
    ),
}


# Vacuum status → HA VacuumActivity
_VACUUM_STATUS_MAP: dict[str, VacuumActivity] = {
    "cleaning": VacuumActivity.CLEANING,
    "running": VacuumActivity.CLEANING,
    "paused": VacuumActivity.PAUSED,
    "returning": VacuumActivity.RETURNING,
    "docked": VacuumActivity.DOCKED,
    "charging": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
    "error": VacuumActivity.ERROR,
}


def map_vacuum_status(raw: str | None) -> VacuumActivity | None:
    """Sber vacuum_cleaner_status → HA VacuumActivity. None если нет state."""
    if raw is None:
        return None
    return _VACUUM_STATUS_MAP.get(str(raw), VacuumActivity.IDLE)


# =============================================================================
# Helpers
# =============================================================================
def _state_value(bundle: SberStateBundle, key: str) -> Any:
    return bundle.value_of(key)


def _on_off_state(value: Any) -> str:
    return STATE_ON if value else STATE_OFF


def _common_sensors(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    """Создать battery/signal sensor если значение есть в bundle."""
    out: list[HaEntityData] = []
    for spec in _COMMON_SENSORS:
        v = _state_value(bundle, spec.key)
        if v is None:
            continue
        out.append(
            _build_sensor(device_id, name, category, spec, v)
        )
    return out


def _common_binary_sensors(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    out: list[HaEntityData] = []
    for spec in _COMMON_BINARY_SENSORS:
        v = _state_value(bundle, spec.key)
        if v is None:
            continue
        out.append(_build_extra_binary(device_id, name, category, spec, v))
    return out


def _category_extra_sensors(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    out: list[HaEntityData] = []
    for spec in _CATEGORY_EXTRA_SENSORS.get(category, ()):
        v = _state_value(bundle, spec.key)
        if v is None:
            continue
        out.append(_build_sensor(device_id, name, category, spec, v))
    return out


def _category_extra_binary_sensors(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    out: list[HaEntityData] = []
    for spec in _CATEGORY_EXTRA_BINARY_SENSORS.get(category, ()):
        v = _state_value(bundle, spec.key)
        if v is None:
            continue
        out.append(_build_extra_binary(device_id, name, category, spec, v))
    return out


def _category_extra_switches(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    """Доп. switch'и (child_lock/night_mode/...) для категории."""
    out: list[HaEntityData] = []
    for spec in _CATEGORY_EXTRA_SWITCHES.get(category, ()):
        v = _state_value(bundle, spec.key)
        if v is None:
            # Если feature не присутствует в bundle — entity не создаётся
            # (HA не нужно показывать кнопки, которых не существует).
            continue
        out.append(
            HaEntityData(
                platform=Platform.SWITCH,
                unique_id=f"{device_id}_{spec.suffix}",
                name=f"{name} {spec.suffix.replace('_', ' ').title()}",
                state=_on_off_state(v),
                state_attribute_key=spec.key,
                entity_category=spec.entity_category,
                icon=spec.icon,
                sber_category=category,
            )
        )
    return out


def _category_selects(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    """SELECT сущность создаётся только если feature присутствует в bundle.

    Это согласовано с registry.py — там SELECT создавался только когда ключ
    существовал в desired_state/attributes устройства.
    """
    out: list[HaEntityData] = []
    for spec in _CATEGORY_SELECTS.get(category, ()):
        v = _state_value(bundle, spec.key)
        if v is None:
            continue
        out.append(
            HaEntityData(
                platform=Platform.SELECT,
                unique_id=f"{device_id}_{spec.suffix}",
                name=f"{name} {spec.suffix.replace('_', ' ').title()}",
                state=v,
                state_attribute_key=spec.key,
                options=spec.options,
                icon=spec.icon,
                entity_category=spec.entity_category,
                sber_category=category,
            )
        )
    return out


def _category_numbers(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    """NUMBER создаётся только если feature присутствует в bundle."""
    out: list[HaEntityData] = []
    for spec in _CATEGORY_NUMBERS.get(category, ()):
        raw = _state_value(bundle, spec.key)
        if raw is None:
            continue
        state = float(raw) * spec.scale
        out.append(
            HaEntityData(
                platform=Platform.NUMBER,
                unique_id=f"{device_id}_{spec.suffix}",
                name=f"{name} {spec.suffix.replace('_', ' ').title()}",
                state=state,
                state_attribute_key=spec.key,
                unit_of_measurement=spec.unit,
                min_value=spec.min_value,
                max_value=spec.max_value,
                step=spec.step,
                scale=spec.scale,
                icon=spec.icon,
                entity_category=spec.entity_category,
                sber_category=category,
            )
        )
    return out


def _category_buttons(
    device_id: str, name: str, *, category: str
) -> list[HaEntityData]:
    out: list[HaEntityData] = []
    for spec in _CATEGORY_BUTTONS.get(category, ()):
        out.append(
            HaEntityData(
                platform=Platform.BUTTON,
                unique_id=f"{device_id}_{spec.suffix}",
                name=f"{name} {spec.suffix.replace('_', ' ').title()}",
                state=None,
                state_attribute_key=spec.key,
                command_value=spec.command_value,
                icon=spec.icon,
                sber_category=category,
            )
        )
    return out


def _category_events(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    """Создать EVENT entities только для тех ключей, которые присутствуют в bundle."""
    out: list[HaEntityData] = []
    for spec in _CATEGORY_EVENTS.get(category, ()):
        if _state_value(bundle, spec.key) is None:
            # Создаём entity только если кнопка реально присутствует у устройства.
            continue
        out.append(
            HaEntityData(
                platform=Platform.EVENT,
                unique_id=f"{device_id}_{spec.suffix}",
                name=f"{name} {spec.suffix.replace('_', ' ').title()}",
                state=_state_value(bundle, spec.key),
                state_attribute_key=spec.key,
                event_types=spec.event_types,
                sber_category=category,
            )
        )
    return out


def _build_sensor(
    device_id: str,
    name: str,
    category: str,
    spec: _ExtraSensorSpec,
    raw_value: Any,
) -> HaEntityData:
    """Применить scale/as_int → HaEntityData(SENSOR)."""
    val: Any = raw_value
    if spec.scale != 1.0 and val is not None:
        val = float(val) * spec.scale
    if spec.as_int and val is not None:
        val = int(val)
    return HaEntityData(
        platform=Platform.SENSOR,
        unique_id=f"{device_id}_{spec.suffix}",
        name=f"{name} {spec.suffix.replace('_', ' ').title()}",
        state=val,
        device_class=spec.device_class,
        unit_of_measurement=spec.unit,
        state_class=spec.state_class,
        entity_category=spec.entity_category,
        icon=spec.icon,
        suggested_display_precision=spec.suggested_display_precision,
        scale=spec.scale,
        sber_category=category,
        state_attribute_key=spec.key,
    )


def _build_extra_binary(
    device_id: str,
    name: str,
    category: str,
    spec: _ExtraBinarySpec,
    raw_value: Any,
) -> HaEntityData:
    return HaEntityData(
        platform=Platform.BINARY_SENSOR,
        unique_id=f"{device_id}_{spec.suffix}",
        name=f"{name} {spec.suffix.replace('_', ' ').title()}",
        state=_on_off_state(raw_value),
        device_class=spec.device_class,
        entity_category=spec.entity_category,
        icon=spec.icon,
        sber_category=category,
        state_attribute_key=spec.key,
    )


def _all_extras(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    """Собрать ВСЕ дополнительные entities для категории.

    Применяется в каждом _transform_<category> для единообразия:
    common_sensors + extra_sensors + extra_binary + common_binary + extra_switches +
    selects + numbers + buttons.
    """
    out: list[HaEntityData] = []
    out.extend(_common_sensors(device_id, name, bundle, category=category))
    out.extend(_category_extra_sensors(device_id, name, bundle, category=category))
    out.extend(_common_binary_sensors(device_id, name, bundle, category=category))
    out.extend(
        _category_extra_binary_sensors(device_id, name, bundle, category=category)
    )
    out.extend(_category_extra_switches(device_id, name, bundle, category=category))
    out.extend(_category_selects(device_id, name, bundle, category=category))
    out.extend(_category_numbers(device_id, name, bundle, category=category))
    out.extend(_category_buttons(device_id, name, category=category))
    return out


# =============================================================================
# Per-category transformers
# =============================================================================
def _transform_light(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str = "light"
) -> list[HaEntityData]:
    is_on = _state_value(bundle, "on_off")
    brightness_raw = _state_value(bundle, "light_brightness")
    color_obj = _state_value(bundle, "light_colour")

    attrs: dict[str, Any] = {}
    if brightness_raw is not None:
        # Стандартный HA helper: масштабирование raw 100..900 → HA 1..255.
        # Точный per-device range применяется в платформе (из device.attributes).
        attrs["brightness"] = value_to_brightness(
            _SBER_BRIGHTNESS_RANGE, int(brightness_raw)
        )
    if isinstance(color_obj, HsvColor):
        attrs["hs_color"] = color_obj.to_ha_hs()
    color_temp = _state_value(bundle, "light_colour_temp")
    if color_temp is not None:
        attrs["color_temp"] = int(color_temp)
    mode = _state_value(bundle, "light_mode")
    if mode is not None:
        attrs["light_mode"] = mode

    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.LIGHT,
            unique_id=device_id,
            name=name,
            state=_on_off_state(is_on),
            attributes=attrs,
            sber_category=category,
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category=category))
    return out


def _transform_socket(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str = "socket"
) -> list[HaEntityData]:
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.SWITCH,
            unique_id=device_id,
            name=name,
            state=_on_off_state(_state_value(bundle, "on_off")),
            sber_category=category,
        ),
    ]
    voltage = _state_value(bundle, "cur_voltage") or _state_value(bundle, "voltage")
    if voltage is not None:
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="cur_voltage", suffix="voltage",
                raw_value=voltage, category=category,
                name_suffix="Voltage",
            )
        )
    current = _state_value(bundle, "cur_current") or _state_value(bundle, "current")
    if current is not None:
        # Sber wire: INTEGER в Amperes (НЕ mA, как раньше делали * 0.001).
        # Подтверждено через MQTT-SberGate sister project.
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="cur_current", suffix="current",
                raw_value=current, category=category,
                name_suffix="Current",
            )
        )
    power = _state_value(bundle, "cur_power") or _state_value(bundle, "power")
    if power is not None:
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="cur_power", suffix="power",
                raw_value=power, category=category,
                name_suffix="Power",
            )
        )
    out.extend(_all_extras(device_id, name, bundle, category=category))
    return out


def _transform_relay(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    return _transform_socket(device_id, name, bundle, category="relay")


def _build_from_codec(
    *,
    device_id: str,
    name: str,
    feature: str,
    suffix: str,
    raw_value: Any,
    category: str,
    name_suffix: str | None = None,
) -> HaEntityData:
    """Build HaEntityData(SENSOR) using FEATURE_CODECS metadata."""
    codec = FEATURE_CODECS[feature]
    label = name_suffix or suffix.replace("_", " ").title()
    return HaEntityData(
        platform=Platform.SENSOR,
        unique_id=f"{device_id}_{suffix}",
        name=f"{name} {label}",
        state=codec.to_ha(raw_value),
        device_class=codec.device_class,
        unit_of_measurement=codec.unit_of_measurement,
        state_class=codec.state_class,
        entity_category=codec.entity_category,
        suggested_display_precision=codec.suggested_display_precision,
        icon=codec.icon,
        state_attribute_key=feature,
        sber_category=category,
    )


def _transform_temp_sensor(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    out: list[HaEntityData] = []
    cat = "sensor_temp"
    t = _state_value(bundle, "temperature")
    if t is not None:
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="temperature", suffix="temperature",
                raw_value=t, category=cat,
                name_suffix="Temperature",
            )
        )
    h = _state_value(bundle, "humidity")
    if h is not None:
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="humidity", suffix="humidity",
                raw_value=h, category=cat,
                name_suffix="Humidity",
            )
        )
    p = _state_value(bundle, "air_pressure")
    if p is not None:
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="air_pressure", suffix="pressure",
                raw_value=p, category=cat,
                name_suffix="Pressure",
            )
        )
    out.extend(_all_extras(device_id, name, bundle, category=cat))
    return out


def _transform_binary_sensor(
    device_id: str,
    name: str,
    bundle: SberStateBundle,
    *,
    category: str,
    state_key: str,
    device_class: BinarySensorDeviceClass,
) -> list[HaEntityData]:
    out: list[HaEntityData] = []
    val = _state_value(bundle, state_key)
    if val is not None:
        out.append(
            HaEntityData(
                platform=Platform.BINARY_SENSOR,
                unique_id=device_id,
                name=name,
                state=_on_off_state(val),
                device_class=device_class,
                state_attribute_key=state_key,
                sber_category=category,
            )
        )
    out.extend(_all_extras(device_id, name, bundle, category=category))
    return out


# Sber open_state → HA CoverState
_OPEN_STATE_MAP: dict[str, str] = {
    "open": CoverState.OPEN,
    "opened": CoverState.OPEN,
    "close": CoverState.CLOSED,
    "closed": CoverState.CLOSED,
    "opening": CoverState.OPENING,
    "closing": CoverState.CLOSING,
}

# Sber category → HA CoverDeviceClass
_COVER_DEVICE_CLASS: dict[str, CoverDeviceClass | None] = {
    "curtain": CoverDeviceClass.CURTAIN,
    "window_blind": CoverDeviceClass.BLIND,
    "gate": CoverDeviceClass.GATE,
    "valve": None,
}


def _transform_cover(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    pos = _state_value(bundle, "open_percentage")
    raw_state = str(_state_value(bundle, "open_state") or "closed")
    ha_state = _OPEN_STATE_MAP.get(raw_state, CoverState.CLOSED)
    attrs: dict[str, Any] = {}
    if pos is not None:
        attrs["current_position"] = int(pos)
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.COVER,
            unique_id=device_id,
            name=name,
            state=ha_state,
            attributes=attrs,
            sber_category=category,
            device_class=_COVER_DEVICE_CLASS.get(category),
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category=category))
    return out


def _build_hvac_maps() -> tuple[dict[str, Any], dict[Any, str]]:
    """Lazy-init HVAC maps (HA enum import — внутри функции для test isolation)."""
    from homeassistant.components.climate import HVACMode

    sber_to_ha: dict[str, Any] = {
        "cool": HVACMode.COOL,
        "heat": HVACMode.HEAT,
        "dry": HVACMode.DRY,
        "fan": HVACMode.FAN_ONLY,
        "fan_only": HVACMode.FAN_ONLY,
        "auto": HVACMode.AUTO,
    }
    ha_to_sber: dict[Any, str] = {
        HVACMode.AUTO: "auto",
        HVACMode.COOL: "cool",
        HVACMode.HEAT: "heat",
        HVACMode.DRY: "dry",
        HVACMode.FAN_ONLY: "fan_only",
    }
    return sber_to_ha, ha_to_sber


def map_hvac_mode(sber_mode: str | None, *, is_on: bool) -> Any:
    """Sber hvac_work_mode → HA HVACMode enum.

    Если is_on==False → HVACMode.OFF. Иначе мап через таблицу, fallback HVACMode.AUTO.
    """
    from homeassistant.components.climate import HVACMode

    if not is_on:
        return HVACMode.OFF
    if sber_mode is None:
        return HVACMode.AUTO
    sber_to_ha, _ = _build_hvac_maps()
    return sber_to_ha.get(str(sber_mode), HVACMode.AUTO)


def map_hvac_mode_to_sber(ha_mode: Any) -> str | None:
    """HA HVACMode → Sber hvac_work_mode wire value.

    Возвращает None для OFF (выключение делается отдельной командой on_off=False).
    """
    from homeassistant.components.climate import HVACMode

    if ha_mode is None or ha_mode == HVACMode.OFF:
        return None
    _, ha_to_sber = _build_hvac_maps()
    return ha_to_sber.get(ha_mode, str(ha_mode))


def _transform_climate(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    is_on = bool(_state_value(bundle, "on_off"))
    target = _state_value(bundle, "hvac_temp_set")
    current = _state_value(bundle, "temperature")
    raw_mode = _state_value(bundle, "hvac_work_mode")
    ha_state = map_hvac_mode(raw_mode, is_on=is_on)

    attrs: dict[str, Any] = {}
    if target is not None:
        attrs["temperature"] = int(target)
    if current is not None:
        attrs["current_temperature"] = float(current)
    fan = _state_value(bundle, "hvac_air_flow_power")
    if fan is not None:
        attrs["fan_mode"] = fan
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.CLIMATE,
            unique_id=device_id,
            name=name,
            state=ha_state,
            attributes=attrs,
            sber_category=category,
        ),
    ]
    # Climate often has temperature/humidity reported as separate sensors too.
    t = _state_value(bundle, "temperature")
    if t is not None:
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="temperature", suffix="temperature",
                raw_value=t, category=category,
                name_suffix="Temperature",
            )
        )
    h = _state_value(bundle, "humidity")
    if h is not None and category == "hvac_ac":
        out.append(
            _build_from_codec(
                device_id=device_id, name=name,
                feature="humidity", suffix="humidity",
                raw_value=h, category=category,
                name_suffix="Humidity",
            )
        )
    out.extend(_all_extras(device_id, name, bundle, category=category))
    return out


def _transform_kettle(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.SWITCH,
            unique_id=device_id,
            name=name,
            state=_on_off_state(_state_value(bundle, "on_off")),
            sber_category="kettle",
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category="kettle"))
    return out


def _transform_tv(device_id: str, name: str, bundle: SberStateBundle) -> list[HaEntityData]:
    is_on = _state_value(bundle, "on_off")
    volume_raw = _state_value(bundle, "volume_int")
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.MEDIA_PLAYER,
            unique_id=device_id,
            name=name,
            state=STATE_ON if is_on else STATE_OFF,
            attributes={
                "source": _state_value(bundle, "source"),
                "volume_level": volume_raw / 100.0 if volume_raw is not None else None,
                "is_volume_muted": _state_value(bundle, "mute"),
            },
            sber_category="tv",
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category="tv"))
    return out


def _transform_vacuum(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    raw_status = _state_value(bundle, "vacuum_cleaner_status")
    activity = map_vacuum_status(raw_status)
    battery = _state_value(bundle, "battery_percentage")
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.VACUUM,
            unique_id=device_id,
            name=name,
            state=activity,
            attributes={
                "battery_level": int(battery) if battery is not None else None,
            },
            sber_category="vacuum_cleaner",
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category="vacuum_cleaner"))
    return out


def _transform_intercom(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    # Primary intercom entity — call status (всегда создаём, даже если value=None)
    out: list[HaEntityData] = []
    # incoming_call берётся из _CATEGORY_EXTRA_BINARY_SENSORS["intercom"]
    out.extend(_all_extras(device_id, name, bundle, category="intercom"))
    out.extend(_category_events(device_id, name, bundle, category="intercom"))
    return out


def _transform_humidifier(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.HUMIDIFIER,
            unique_id=device_id,
            name=name,
            state=_on_off_state(_state_value(bundle, "on_off")),
            attributes={
                "humidity": _state_value(bundle, "hvac_humidity_set"),
                "current_humidity": _state_value(bundle, "humidity"),
                "mode": _state_value(bundle, "hvac_air_flow_power"),
            },
            options=("auto", "low", "medium", "high", "turbo"),
            min_value=30,
            max_value=80,
            sber_category="hvac_humidifier",
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category="hvac_humidifier"))
    return out


def _transform_fan(
    device_id: str, name: str, bundle: SberStateBundle, *, category: str
) -> list[HaEntityData]:
    # preset_mode_options различаются для hvac_fan vs hvac_air_purifier.
    if category == "hvac_air_purifier":
        preset_modes: tuple[str, ...] = ("auto", "low", "medium", "high", "turbo")
    else:
        preset_modes = ("low", "medium", "high", "turbo")
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.FAN,
            unique_id=device_id,
            name=name,
            state=_on_off_state(_state_value(bundle, "on_off")),
            attributes={
                "preset_mode": _state_value(bundle, "hvac_air_flow_power"),
            },
            options=preset_modes,
            sber_category=category,
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category=category))
    return out


def _transform_hub(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    out: list[HaEntityData] = [
        HaEntityData(
            platform=Platform.BINARY_SENSOR,
            unique_id=device_id,
            name=name,
            state=_on_off_state(_state_value(bundle, "online")),
            device_class=BinarySensorDeviceClass.CONNECTIVITY,
            state_attribute_key="online",
            sber_category="hub",
        ),
    ]
    out.extend(_all_extras(device_id, name, bundle, category="hub"))
    return out


def _transform_scenario_button(
    device_id: str, name: str, bundle: SberStateBundle
) -> list[HaEntityData]:
    """scenario_button — только EVENT entities (никакого primary state)."""
    return _category_events(device_id, name, bundle, category="scenario_button")


# =============================================================================
# Dispatcher
# =============================================================================
TransformFn = Callable[[str, str, SberStateBundle], list[HaEntityData]]

_DISPATCH: dict[str, TransformFn] = {
    "light": _transform_light,
    "led_strip": lambda d, n, b: _transform_light(d, n, b, category="led_strip"),
    "socket": _transform_socket,
    "relay": _transform_relay,
    "sensor_temp": _transform_temp_sensor,
    "sensor_water_leak": lambda d, n, b: _transform_binary_sensor(
        d, n, b, category="sensor_water_leak", state_key="water_leak_state",
        device_class=BinarySensorDeviceClass.MOISTURE,
    ),
    "sensor_door": lambda d, n, b: _transform_binary_sensor(
        d, n, b, category="sensor_door", state_key="doorcontact_state",
        device_class=BinarySensorDeviceClass.DOOR,
    ),
    "sensor_pir": lambda d, n, b: _transform_binary_sensor(
        d, n, b, category="sensor_pir", state_key="motion_state",
        device_class=BinarySensorDeviceClass.MOTION,
    ),
    "sensor_smoke": lambda d, n, b: _transform_binary_sensor(
        d, n, b, category="sensor_smoke", state_key="smoke_state",
        device_class=BinarySensorDeviceClass.SMOKE,
    ),
    "sensor_gas": lambda d, n, b: _transform_binary_sensor(
        d, n, b, category="sensor_gas", state_key="gas_leak_state",
        device_class=BinarySensorDeviceClass.GAS,
    ),
    "curtain": lambda d, n, b: _transform_cover(d, n, b, category="curtain"),
    "window_blind": lambda d, n, b: _transform_cover(d, n, b, category="window_blind"),
    "gate": lambda d, n, b: _transform_cover(d, n, b, category="gate"),
    "valve": lambda d, n, b: _transform_cover(d, n, b, category="valve"),
    "hvac_ac": lambda d, n, b: _transform_climate(d, n, b, category="hvac_ac"),
    "hvac_heater": lambda d, n, b: _transform_climate(d, n, b, category="hvac_heater"),
    "hvac_radiator": lambda d, n, b: _transform_climate(d, n, b, category="hvac_radiator"),
    "hvac_boiler": lambda d, n, b: _transform_climate(d, n, b, category="hvac_boiler"),
    "hvac_underfloor_heating": lambda d, n, b: _transform_climate(
        d, n, b, category="hvac_underfloor_heating"
    ),
    "hvac_fan": lambda d, n, b: _transform_fan(d, n, b, category="hvac_fan"),
    "hvac_air_purifier": lambda d, n, b: _transform_fan(d, n, b, category="hvac_air_purifier"),
    "hvac_humidifier": _transform_humidifier,
    "kettle": _transform_kettle,
    "vacuum_cleaner": _transform_vacuum,
    "tv": _transform_tv,
    "intercom": _transform_intercom,
    "scenario_button": _transform_scenario_button,
    "hub": _transform_hub,
}


def sber_to_ha(
    category: str,
    device_id: str,
    name: str,
    bundle: SberStateBundle,
) -> list[HaEntityData]:
    """Превратить Sber-устройство (категория + bundle states) в список HA-сущностей.

    Args:
        category: Sber image_set_type (e.g. `"light"`).
        device_id: Sber device UUID.
        name: display name.
        bundle: SberStateBundle (декодированный из wire через Codec).

    Returns:
        Список HaEntityData. Пустой если категория unknown.
    """
    fn = _DISPATCH.get(category)
    if fn is None:
        return []
    return fn(device_id, name, bundle)


def brightness_ha_to_sber(ha_brightness: int) -> int:
    """HA brightness 0..255 → Sber light_brightness 100..900.

    Использует стандартный HA helper `brightness_to_value`.
    """
    if ha_brightness <= 0:
        return _SBER_BRIGHTNESS_RANGE[0]
    return min(
        _SBER_BRIGHTNESS_RANGE[1],
        round(brightness_to_value(_SBER_BRIGHTNESS_RANGE, ha_brightness)),
    )


__all__ = [
    "HaEntityData",
    "brightness_ha_to_sber",
    "map_hvac_mode",
    "map_hvac_mode_to_sber",
    "map_vacuum_status",
    "sber_to_ha",
]
