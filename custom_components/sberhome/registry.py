"""Declarative device registry: feature → entity descriptors.

Маппит `image_set_type` устройства в категорию (по sber_full_spec.json),
а затем описывает какие сущности HA создавать по features.

Добавить новое устройство = добавить строку в IMAGE_TYPE_TO_CATEGORY
и при необходимости категорию в нужный CATEGORY_* словарь.
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.cover import CoverDeviceClass
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


# =============================================================================
# Dataclass-дескрипторы
# =============================================================================


@dataclass(frozen=True)
class SensorSpec:
    key: str
    suffix: str
    device_class: SensorDeviceClass | None = None
    unit: str | None = None
    state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT
    entity_category: EntityCategory | None = None
    precision: int | None = None
    scale: float = 1.0
    as_int: bool = False
    enabled_by_default: bool = True
    icon: str | None = None


@dataclass(frozen=True)
class BinarySensorSpec:
    key: str
    suffix: str
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None
    enabled_by_default: bool = True
    icon: str | None = None


@dataclass(frozen=True)
class SwitchSpec:
    """on_off switch."""

    key: str = "on_off"
    suffix: str = ""


@dataclass(frozen=True)
class NumberSpec:
    """Числовая настройка через desired_state.integer_value."""

    key: str
    suffix: str
    unit: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    entity_category: EntityCategory | None = None
    icon: str | None = None
    scale: float = 1.0  # raw → value (domain×scale); обратное для set


@dataclass(frozen=True)
class SelectSpec:
    """Enum-настройка."""

    key: str
    suffix: str
    options: tuple[str, ...]
    entity_category: EntityCategory | None = None
    icon: str | None = None


@dataclass(frozen=True)
class CoverSpec:
    """Cover (шторы, ворота, клапан)."""

    position_key: str = "open_percentage"  # reported_state 0..100
    set_key: str = "open_set"  # desired_state target %
    state_key: str = "open_state"  # opening/closing/opened/closed/stop
    device_class: CoverDeviceClass | None = None
    supports_set_position: bool = True
    supports_stop: bool = True


@dataclass(frozen=True)
class ClimateSpec:
    """HVAC-устройство."""

    temperature_key: str | None = "hvac_temp_set"
    current_temp_key: str | None = None  # e.g. "temperature" из reported_state
    fan_mode_key: str | None = None  # "hvac_air_flow_power"
    fan_modes: tuple[str, ...] = ()
    hvac_modes_key: str | None = None  # "hvac_work_mode"
    hvac_modes: tuple[str, ...] = ()
    swing_key: str | None = None
    humidity_key: str | None = None
    min_temp: float = 7
    max_temp: float = 35
    step: float = 1


@dataclass(frozen=True)
class FanSpec:
    speed_key: str | None = "hvac_air_flow_power"
    speeds: tuple[str, ...] = ("auto", "low", "medium", "high", "turbo")


@dataclass(frozen=True)
class HumidifierSpec:
    target_humidity_key: str | None = "hvac_humidity_set"
    mode_key: str | None = None
    modes: tuple[str, ...] = ()
    min_humidity: int = 30
    max_humidity: int = 80


@dataclass(frozen=True)
class MediaPlayerSpec:
    """TV / media_player."""

    source_key: str = "source"
    sources: tuple[str, ...] = ()
    volume_key: str = "volume_int"
    mute_key: str = "mute"
    channel_key: str = "channel_int"
    direction_key: str = "direction"
    custom_key_field: str = "custom_key"
    volume_max: int = 100


@dataclass(frozen=True)
class VacuumSpec:
    """Робот-пылесос."""

    command_key: str = "vacuum_cleaner_command"  # start/pause/return_to_base/locate
    status_key: str = "vacuum_cleaner_status"
    program_key: str = "vacuum_cleaner_program"
    programs: tuple[str, ...] = ("perimeter", "spot", "smart")
    cleaning_type_key: str = "vacuum_cleaner_cleaning_type"


@dataclass(frozen=True)
class ExtraSwitchSpec:
    """Дополнительный switch у сложного устройства (child_lock, night_mode)."""

    key: str
    suffix: str
    entity_category: EntityCategory | None = EntityCategory.CONFIG
    icon: str | None = None


@dataclass(frozen=True)
class EventSpec:
    """Одна кнопка сценарного выключателя."""

    key: str  # reported_state key, e.g. "button_1_event"
    suffix: str  # unique_id suffix
    event_types: tuple[str, ...] = ("click", "double_click")


# =============================================================================
# image_set_type → категория (substring match)
# =============================================================================
BINARY_ONLY_ONLINE_CATEGORIES: tuple[str, ...] = ("hub", "intercom")


IMAGE_TYPE_TO_CATEGORY: dict[str, str] = {
    # Lights
    "bulb_sber": "light",
    "ledstrip_sber": "led_strip",
    "led_strip": "led_strip",
    # Switches
    "dt_socket_sber": "socket",
    "socket": "socket",
    "relay": "relay",
    # Climate sensors
    "cat_sensor_temp_humidity": "sensor_temp",
    "sensor_temp": "sensor_temp",
    # Binary sensors
    "dt_sensor_water_leak": "sensor_water_leak",
    "sensor_water_leak": "sensor_water_leak",
    "cat_sensor_door": "sensor_door",
    "sensor_door": "sensor_door",
    "cat_sensor_motion": "sensor_pir",
    "sensor_motion": "sensor_pir",
    "sensor_pir": "sensor_pir",
    "sensor_smoke": "sensor_smoke",
    "sensor_gas": "sensor_gas",
    # Scenario
    "scenario_button": "scenario_button",
    "button_scenario": "scenario_button",
    # Covers
    "curtain": "curtain",
    "gate": "gate",
    "window_blind": "window_blind",
    "valve": "valve",
    # HVAC
    "hvac_ac": "hvac_ac",
    "hvac_heater": "hvac_heater",
    "hvac_radiator": "hvac_radiator",
    "hvac_boiler": "hvac_boiler",
    "hvac_underfloor": "hvac_underfloor_heating",
    "hvac_fan": "hvac_fan",
    "hvac_humidifier": "hvac_humidifier",
    "hvac_air_purifier": "hvac_air_purifier",
    # Appliances
    "kettle": "kettle",
    "vacuum_cleaner": "vacuum_cleaner",
    "tv": "tv",
    "hub": "hub",
    "intercom": "intercom",
}


def resolve_category(device: dict) -> str | None:
    """Определить категорию устройства по image_set_type.

    1. Сначала пробуем точное совпадение (самый надёжный путь).
    2. Далее — substring-match (для совместимости с реальными image_set_type
       вида "bulb_sber", "dt_socket_sber" и пр.).

    Порядок итерации IMAGE_TYPE_TO_CATEGORY сохраняется (Python 3.7+ dict
    insertion order) — более специфичные паттерны должны идти раньше.
    """
    image = device.get("image_set_type") or ""
    if not image:
        return None
    # 1. Exact match
    if image in IMAGE_TYPE_TO_CATEGORY:
        return IMAGE_TYPE_TO_CATEGORY[image]
    # 2. Substring match (fallback)
    for pattern, cat in IMAGE_TYPE_TO_CATEGORY.items():
        if pattern in image:
            return cat
    return None


# =============================================================================
# SENSORS
# =============================================================================
CATEGORY_SENSORS: dict[str, list[SensorSpec]] = {
    "sensor_temp": [
        SensorSpec(
            "temperature",
            "temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            precision=1,
        ),
        SensorSpec(
            "humidity",
            "humidity",
            SensorDeviceClass.HUMIDITY,
            PERCENTAGE,
            precision=0,
        ),
        SensorSpec(
            "air_pressure",
            "air_pressure",
            SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            UnitOfPressure.HPA,
            precision=0,
        ),
    ],
    "socket": [
        SensorSpec(
            "cur_voltage",
            "voltage",
            SensorDeviceClass.VOLTAGE,
            UnitOfElectricPotential.VOLT,
            precision=1,
        ),
        SensorSpec(
            "cur_current",
            "current",
            SensorDeviceClass.CURRENT,
            UnitOfElectricCurrent.AMPERE,
            precision=2,
            scale=0.001,  # mA → A
        ),
        SensorSpec(
            "cur_power",
            "power",
            SensorDeviceClass.POWER,
            UnitOfPower.WATT,
            precision=1,
        ),
    ],
    "relay": [
        SensorSpec(
            "cur_voltage",
            "voltage",
            SensorDeviceClass.VOLTAGE,
            UnitOfElectricPotential.VOLT,
            precision=1,
        ),
        SensorSpec(
            "cur_current",
            "current",
            SensorDeviceClass.CURRENT,
            UnitOfElectricCurrent.AMPERE,
            precision=2,
            scale=0.001,
        ),
        SensorSpec(
            "cur_power",
            "power",
            SensorDeviceClass.POWER,
            UnitOfPower.WATT,
            precision=1,
        ),
    ],
    "kettle": [
        SensorSpec(
            "kitchen_water_temperature",
            "water_temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            precision=0,
        ),
        SensorSpec(
            "kitchen_water_level",
            "water_level",
            unit=PERCENTAGE,
            precision=0,
        ),
    ],
    "vacuum_cleaner": [
        SensorSpec(
            "vacuum_cleaner_status",
            "status",
            state_class=None,
            enabled_by_default=True,
        ),
    ],
    # HVAC текущая температура/влажность (как отдельные sensor-сущности).
    "hvac_ac": [
        SensorSpec(
            "temperature",
            "temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            precision=1,
        ),
        SensorSpec(
            "humidity",
            "humidity",
            SensorDeviceClass.HUMIDITY,
            PERCENTAGE,
            precision=0,
        ),
    ],
    "hvac_heater": [
        SensorSpec(
            "temperature",
            "temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            precision=1,
        ),
    ],
    "hvac_radiator": [
        SensorSpec(
            "temperature",
            "temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            precision=1,
        ),
    ],
    "hvac_boiler": [
        SensorSpec(
            "temperature",
            "temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            precision=1,
        ),
    ],
    "hvac_underfloor_heating": [
        SensorSpec(
            "temperature",
            "temperature",
            SensorDeviceClass.TEMPERATURE,
            UnitOfTemperature.CELSIUS,
            precision=1,
        ),
    ],
    "hvac_humidifier": [
        SensorSpec(
            "humidity",
            "humidity",
            SensorDeviceClass.HUMIDITY,
            PERCENTAGE,
            precision=0,
        ),
        SensorSpec(
            "hvac_water_level",
            "water_level",
            unit=PERCENTAGE,
            precision=0,
            icon="mdi:water-percent",
        ),
        SensorSpec(
            "hvac_water_percentage",
            "water_percentage",
            unit=PERCENTAGE,
            precision=0,
            icon="mdi:water",
        ),
    ],
}

# Общие сенсоры: создаются для любой категории, если feature есть в device JSON
COMMON_SENSORS: list[SensorSpec] = [
    SensorSpec(
        "battery_percentage",
        "battery",
        SensorDeviceClass.BATTERY,
        PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        as_int=True,
    ),
    SensorSpec(
        "signal_strength",
        "signal_strength",
        SensorDeviceClass.SIGNAL_STRENGTH,
        "dBm",
        entity_category=EntityCategory.DIAGNOSTIC,
        as_int=True,
        enabled_by_default=False,
    ),
]


# =============================================================================
# BINARY SENSORS
# =============================================================================
CATEGORY_BINARY_SENSORS: dict[str, list[BinarySensorSpec]] = {
    "sensor_water_leak": [
        BinarySensorSpec("water_leak_state", "", BinarySensorDeviceClass.MOISTURE),
    ],
    "sensor_door": [
        BinarySensorSpec("doorcontact_state", "", BinarySensorDeviceClass.DOOR),
        BinarySensorSpec(
            "tamper_alarm",
            "tamper",
            BinarySensorDeviceClass.TAMPER,
            EntityCategory.DIAGNOSTIC,
        ),
    ],
    "sensor_pir": [
        BinarySensorSpec("motion_state", "", BinarySensorDeviceClass.MOTION),
    ],
    "sensor_smoke": [
        BinarySensorSpec("smoke_state", "", BinarySensorDeviceClass.SMOKE),
    ],
    "sensor_gas": [
        BinarySensorSpec("gas_leak_state", "", BinarySensorDeviceClass.GAS),
    ],
    "kettle": [
        BinarySensorSpec(
            "kitchen_water_low_level",
            "water_low_level",
            BinarySensorDeviceClass.PROBLEM,
            icon="mdi:water-alert",
        ),
    ],
    "hvac_humidifier": [
        BinarySensorSpec(
            "hvac_water_low_level",
            "water_low_level",
            BinarySensorDeviceClass.PROBLEM,
            icon="mdi:water-alert",
        ),
        BinarySensorSpec(
            "hvac_replace_filter",
            "replace_filter",
            BinarySensorDeviceClass.PROBLEM,
            EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
        ),
        BinarySensorSpec(
            "hvac_replace_ionizator",
            "replace_ionizator",
            BinarySensorDeviceClass.PROBLEM,
            EntityCategory.DIAGNOSTIC,
            icon="mdi:flash",
        ),
    ],
    "hvac_air_purifier": [
        BinarySensorSpec(
            "hvac_replace_filter",
            "replace_filter",
            BinarySensorDeviceClass.PROBLEM,
            EntityCategory.DIAGNOSTIC,
            icon="mdi:air-filter",
        ),
        BinarySensorSpec(
            "hvac_replace_ionizator",
            "replace_ionizator",
            BinarySensorDeviceClass.PROBLEM,
            EntityCategory.DIAGNOSTIC,
            icon="mdi:flash",
        ),
    ],
    "intercom": [
        BinarySensorSpec(
            "incoming_call",
            "incoming_call",
            BinarySensorDeviceClass.OCCUPANCY,
            icon="mdi:phone-ring",
        ),
    ],
}

COMMON_BINARY_SENSORS: list[BinarySensorSpec] = [
    BinarySensorSpec(
        "battery_low_power",
        "battery_low",
        BinarySensorDeviceClass.BATTERY,
        EntityCategory.DIAGNOSTIC,
    ),
]


# =============================================================================
# SWITCHES (простой on_off без яркости/цвета)
# =============================================================================
CATEGORY_SWITCHES: dict[str, SwitchSpec] = {
    "socket": SwitchSpec(),
    "relay": SwitchSpec(),
    "kettle": SwitchSpec(),
    # sensor_gas / sensor_smoke имеют alarm_mute как switch
    # (обрабатывается через CATEGORY_EXTRA_SWITCHES)
}


# =============================================================================
# NUMBERS (настраиваемые числовые значения)
# =============================================================================
CATEGORY_NUMBERS: dict[str, list[NumberSpec]] = {
    "kettle": [
        NumberSpec(
            "kitchen_water_temperature_set",
            "target_temperature",
            unit=UnitOfTemperature.CELSIUS,
            min_value=60,
            max_value=100,
            step=10,
            icon="mdi:thermometer",
        ),
    ],
    "led_strip": [
        NumberSpec(
            "sleep_timer",
            "sleep_timer",
            unit=UnitOfTime.MINUTES,
            min_value=0,
            max_value=720,
            step=1,
            entity_category=EntityCategory.CONFIG,
            icon="mdi:timer",
        ),
    ],
    "hvac_ac": [
        NumberSpec(
            "hvac_humidity_set",
            "target_humidity",
            unit=PERCENTAGE,
            min_value=30,
            max_value=80,
            step=5,
            icon="mdi:water-percent",
        ),
    ],
    "window_blind": [
        NumberSpec(
            "light_transmission_percentage",
            "light_transmission",
            unit=PERCENTAGE,
            min_value=0,
            max_value=100,
            step=1,
            icon="mdi:weather-sunny",
        ),
    ],
}


# =============================================================================
# COVERS
# =============================================================================
CATEGORY_COVERS: dict[str, CoverSpec] = {
    "curtain": CoverSpec(device_class=CoverDeviceClass.CURTAIN),
    "window_blind": CoverSpec(device_class=CoverDeviceClass.BLIND),
    "gate": CoverSpec(device_class=CoverDeviceClass.GATE),
    # valve: по spec имеет только open_set (0/100), позиционирование не всегда
    # поддерживается — отключаем SET_POSITION и STOP, оставляя open/close.
    "valve": CoverSpec(
        device_class=None,
        supports_set_position=False,
        supports_stop=False,
    ),
}


# =============================================================================
# CLIMATE / FAN / HUMIDIFIER
# =============================================================================
# Стандартный набор HVAC work modes сбер → HA маппинг делается в platform-коде.
CATEGORY_CLIMATE: dict[str, ClimateSpec] = {
    "hvac_ac": ClimateSpec(
        temperature_key="hvac_temp_set",
        current_temp_key="temperature",
        fan_mode_key="hvac_air_flow_power",
        fan_modes=("auto", "low", "medium", "high", "turbo"),
        hvac_modes_key="hvac_work_mode",
        hvac_modes=("auto", "cool", "heat", "dry", "fan_only"),
        humidity_key="humidity",
        min_temp=16,
        max_temp=30,
        step=1,
    ),
    "hvac_heater": ClimateSpec(
        temperature_key="hvac_temp_set",
        current_temp_key="temperature",
        fan_mode_key="hvac_air_flow_power",
        fan_modes=("auto", "low", "medium", "high", "turbo"),
        min_temp=7,
        max_temp=30,
        step=1,
    ),
    # Диапазоны min/max/step — строго по sber_full_spec.json
    "hvac_radiator": ClimateSpec(
        temperature_key="hvac_temp_set",
        current_temp_key="temperature",
        min_temp=25,
        max_temp=40,
        step=5,
    ),
    "hvac_boiler": ClimateSpec(
        temperature_key="hvac_temp_set",
        current_temp_key="temperature",
        min_temp=25,
        max_temp=80,
        step=5,
    ),
    "hvac_underfloor_heating": ClimateSpec(
        temperature_key="hvac_temp_set",
        current_temp_key="temperature",
        min_temp=25,
        max_temp=50,
        step=5,
    ),
}

CATEGORY_FANS: dict[str, FanSpec] = {
    "hvac_fan": FanSpec(
        speed_key="hvac_air_flow_power",
        speeds=("low", "medium", "high", "turbo"),
    ),
    "hvac_air_purifier": FanSpec(
        speed_key="hvac_air_flow_power",
        speeds=("auto", "low", "medium", "high", "turbo"),
    ),
}

CATEGORY_HUMIDIFIERS: dict[str, HumidifierSpec] = {
    "hvac_humidifier": HumidifierSpec(
        target_humidity_key="hvac_humidity_set",
        mode_key="hvac_air_flow_power",
        modes=("auto", "low", "medium", "high", "turbo"),
        min_humidity=30,
        max_humidity=80,
    ),
}


# =============================================================================
# EVENTS (scenario button)
# =============================================================================
CATEGORY_EVENTS: dict[str, list[EventSpec]] = {
    "scenario_button": [
        # Обобщённое событие (для одноклавишных).
        EventSpec("button_event", "button"),
        # Пронумерованные кнопки (1-10).
        *[
            EventSpec(f"button_{i}_event", f"button_{i}")
            for i in range(1, 11)
        ],
        # Направленные кнопки (для кресто-образных / 4-клавишных).
        EventSpec("button_left_event", "button_left"),
        EventSpec("button_right_event", "button_right"),
        EventSpec("button_top_left_event", "button_top_left"),
        EventSpec("button_top_right_event", "button_top_right"),
        EventSpec("button_bottom_left_event", "button_bottom_left"),
        EventSpec("button_bottom_right_event", "button_bottom_right"),
    ],
}


# =============================================================================
# SELECTS (enum-настройки)
# =============================================================================
CATEGORY_SELECTS: dict[str, list[SelectSpec]] = {
    "curtain": [
        SelectSpec(
            "open_rate",
            "open_rate",
            options=("auto", "low", "high"),
            entity_category=EntityCategory.CONFIG,
            icon="mdi:speedometer",
        ),
    ],
    "gate": [
        SelectSpec(
            "open_rate",
            "open_rate",
            options=("auto", "low", "high"),
            entity_category=EntityCategory.CONFIG,
            icon="mdi:speedometer",
        ),
    ],
    "window_blind": [
        SelectSpec(
            "open_rate",
            "open_rate",
            options=("auto", "low", "high"),
            entity_category=EntityCategory.CONFIG,
            icon="mdi:speedometer",
        ),
    ],
    "hvac_ac": [
        SelectSpec(
            "hvac_air_flow_direction",
            "air_flow_direction",
            options=("auto", "top", "middle", "bottom"),
            icon="mdi:air-filter",
        ),
    ],
    "sensor_temp": [
        SelectSpec(
            "sensor_sensitive",
            "sensitivity",
            options=("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
        SelectSpec(
            "temp_unit_view",
            "temp_unit",
            options=("celsius", "fahrenheit"),
            entity_category=EntityCategory.CONFIG,
        ),
    ],
    "sensor_door": [
        SelectSpec(
            "sensor_sensitive",
            "sensitivity",
            options=("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
    ],
    "sensor_pir": [
        SelectSpec(
            "sensor_sensitive",
            "sensitivity",
            options=("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
    ],
    "sensor_gas": [
        SelectSpec(
            "sensor_sensitive",
            "sensitivity",
            options=("auto", "high"),
            entity_category=EntityCategory.CONFIG,
        ),
    ],
    "vacuum_cleaner": [
        SelectSpec(
            "vacuum_cleaner_program",
            "program",
            options=("perimeter", "spot", "smart"),
            icon="mdi:robot-vacuum",
        ),
        SelectSpec(
            "vacuum_cleaner_cleaning_type",
            "cleaning_type",
            options=("dry", "wet", "mixed"),
            icon="mdi:broom",
        ),
    ],
    # hvac_thermostat_mode (heater, boiler, underfloor)
    "hvac_heater": [
        SelectSpec(
            "hvac_thermostat_mode",
            "thermostat_mode",
            options=("auto", "eco", "comfort", "boost"),
            icon="mdi:thermostat",
        ),
    ],
    "hvac_boiler": [
        SelectSpec(
            "hvac_thermostat_mode",
            "thermostat_mode",
            options=("auto", "eco", "comfort", "boost"),
            icon="mdi:thermostat",
        ),
        SelectSpec(
            "hvac_heating_rate",
            "heating_rate",
            options=("slow", "medium", "fast"),
            entity_category=EntityCategory.CONFIG,
            icon="mdi:speedometer",
        ),
    ],
    "hvac_underfloor_heating": [
        SelectSpec(
            "hvac_thermostat_mode",
            "thermostat_mode",
            options=("auto", "eco", "comfort", "boost"),
            icon="mdi:thermostat",
        ),
        SelectSpec(
            "hvac_heating_rate",
            "heating_rate",
            options=("slow", "medium", "fast"),
            entity_category=EntityCategory.CONFIG,
            icon="mdi:speedometer",
        ),
    ],
    "hvac_fan": [
        SelectSpec(
            "hvac_direction_set",
            "direction",
            options=("auto", "top", "middle", "bottom", "swing"),
            icon="mdi:arrow-decision",
        ),
    ],
}


# =============================================================================
# EXTRA SWITCHES (child_lock, night_mode и т.д. — дополнительные toggle на устройстве)
# =============================================================================
CATEGORY_EXTRA_SWITCHES: dict[str, list[ExtraSwitchSpec]] = {
    "socket": [
        ExtraSwitchSpec("child_lock", "child_lock", icon="mdi:lock"),
    ],
    "kettle": [
        ExtraSwitchSpec("child_lock", "child_lock", icon="mdi:lock"),
    ],
    "vacuum_cleaner": [
        ExtraSwitchSpec("child_lock", "child_lock", icon="mdi:lock"),
    ],
    "hvac_ac": [
        ExtraSwitchSpec("hvac_night_mode", "night_mode", icon="mdi:weather-night"),
        ExtraSwitchSpec("hvac_ionization", "ionization", icon="mdi:flash"),
    ],
    "hvac_humidifier": [
        ExtraSwitchSpec("hvac_night_mode", "night_mode", icon="mdi:weather-night"),
        ExtraSwitchSpec("hvac_ionization", "ionization", icon="mdi:flash"),
    ],
    "hvac_air_purifier": [
        ExtraSwitchSpec("hvac_night_mode", "night_mode", icon="mdi:weather-night"),
        ExtraSwitchSpec("hvac_ionization", "ionization", icon="mdi:flash"),
        ExtraSwitchSpec(
            "hvac_aromatization", "aromatization", icon="mdi:scent"
        ),
        ExtraSwitchSpec(
            "hvac_decontaminate", "decontaminate", icon="mdi:shield-sun"
        ),
    ],
    "sensor_gas": [
        ExtraSwitchSpec(
            "alarm_mute",
            "alarm_mute",
            icon="mdi:bell-off",
        ),
    ],
    "sensor_smoke": [
        ExtraSwitchSpec(
            "alarm_mute",
            "alarm_mute",
            icon="mdi:bell-off",
        ),
    ],
}


# =============================================================================
# MEDIA PLAYERS
# =============================================================================
CATEGORY_MEDIA_PLAYERS: dict[str, MediaPlayerSpec] = {
    "tv": MediaPlayerSpec(
        sources=("hdmi1", "hdmi2", "hdmi3", "tv", "av", "content"),
    ),
}


# =============================================================================
# VACUUMS
# =============================================================================
CATEGORY_VACUUMS: dict[str, VacuumSpec] = {
    "vacuum_cleaner": VacuumSpec(),
}
