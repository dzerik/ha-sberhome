"""HA platforms ↔ Sber categories маппинг.

**Single source of truth** для обоих проектов:
- `ha-sberhome` использует чтобы знать какие HA-сущности создавать для Sber-устройства.
- `MQTT-SberGate` использует чтобы знать в какую Sber-категорию публиковать
  HA-entity.

Гибридный режим: использует `homeassistant.const.Platform` enum для type safety
и защиты от опечаток (см. CLAUDE.md → "Архитектурная парадигма").
"""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# ---------------------------------------------------------------------------
# Sber category → primary HA platform(s)
# ---------------------------------------------------------------------------
# Каждая категория Sber может create несколько entities в HA (например socket
# делает switch + 3 sensor'а power monitoring).
CATEGORY_TO_HA_PLATFORMS: Final[dict[str, tuple[Platform, ...]]] = {
    # Lights
    "light": (Platform.LIGHT,),
    "led_strip": (Platform.LIGHT, Platform.NUMBER),  # + sleep_timer
    # Switches with measurement
    "socket": (Platform.SWITCH, Platform.SENSOR, Platform.SWITCH),  # + child_lock
    "relay": (Platform.SWITCH, Platform.SENSOR),
    # Sensors
    "sensor_temp": (Platform.SENSOR, Platform.SELECT),  # + sensitivity
    "sensor_water_leak": (Platform.BINARY_SENSOR,),
    "sensor_door": (Platform.BINARY_SENSOR, Platform.SELECT),
    "sensor_pir": (Platform.BINARY_SENSOR, Platform.SELECT),
    "sensor_smoke": (Platform.BINARY_SENSOR, Platform.SWITCH),  # + alarm_mute
    "sensor_gas": (Platform.BINARY_SENSOR, Platform.SWITCH, Platform.SELECT),
    # Covers
    "curtain": (Platform.COVER, Platform.SELECT),  # + open_rate
    "window_blind": (Platform.COVER, Platform.SELECT, Platform.NUMBER),
    "gate": (Platform.COVER, Platform.SELECT),
    "valve": (Platform.COVER,),
    # HVAC
    "hvac_ac": (Platform.CLIMATE, Platform.SWITCH, Platform.NUMBER),
    "hvac_heater": (Platform.CLIMATE, Platform.SELECT),
    "hvac_radiator": (Platform.CLIMATE,),
    "hvac_boiler": (Platform.CLIMATE, Platform.SELECT),
    "hvac_underfloor_heating": (Platform.CLIMATE, Platform.SELECT),
    "hvac_fan": (Platform.FAN,),
    "hvac_air_purifier": (Platform.FAN, Platform.SWITCH, Platform.BINARY_SENSOR),
    "hvac_humidifier": (Platform.HUMIDIFIER, Platform.SENSOR, Platform.BINARY_SENSOR),
    # Appliances
    "kettle": (Platform.SWITCH, Platform.NUMBER, Platform.SENSOR, Platform.BINARY_SENSOR),
    "vacuum_cleaner": (Platform.VACUUM, Platform.SELECT),
    "tv": (Platform.MEDIA_PLAYER,),
    # Misc
    "scenario_button": (Platform.EVENT,),
    "intercom": (Platform.BINARY_SENSOR, Platform.BUTTON),
    "hub": (Platform.BINARY_SENSOR,),
}


# ---------------------------------------------------------------------------
# Reverse map: HA platform → Sber categories which create that platform
# ---------------------------------------------------------------------------
def _build_reverse() -> dict[Platform, frozenset[str]]:
    rev: dict[Platform, set[str]] = {}
    for cat, platforms in CATEGORY_TO_HA_PLATFORMS.items():
        for p in platforms:
            rev.setdefault(p, set()).add(cat)
    return {k: frozenset(v) for k, v in rev.items()}


HA_PLATFORM_TO_CATEGORIES: Final[dict[Platform, frozenset[str]]] = _build_reverse()


# ---------------------------------------------------------------------------
# Sber feature key → HA attribute name (для transform layer)
# ---------------------------------------------------------------------------
# Только однозначные mapping'и — где HA-attribute напрямую соответствует
# Sber feature. Сложные конверсии (например `light_brightness 100..900` →
# `brightness 0..255`) обрабатываются в transform/sber_to_ha.py.
FEATURE_TO_HA_ATTRIBUTE: Final[dict[str, str]] = {
    # Light
    "on_off": "state",
    "light_brightness": "brightness",
    "light_colour": "hs_color",
    "light_colour_temp": "color_temp",
    # Sensors
    "temperature": "temperature",
    "humidity": "humidity",
    "air_pressure": "pressure",
    "battery_percentage": "battery_level",
    # Cover
    "open_percentage": "current_position",
    # HVAC
    "hvac_temp_set": "temperature",
    "hvac_humidity_set": "humidity",
    "hvac_work_mode": "hvac_mode",
    "hvac_air_flow_power": "fan_mode",
    "hvac_air_flow_direction": "swing_mode",
    # TV
    "volume_int": "volume_level",
    "mute": "is_volume_muted",
    "source": "source",
    "channel_int": "media_channel",
    # Vacuum
    "vacuum_cleaner_status": "state",
}


def platforms_for_category(category: str) -> tuple[Platform, ...]:
    """Return HA-platforms нужные для Sber-категории. () если категория unknown."""
    return CATEGORY_TO_HA_PLATFORMS.get(category, ())


def categories_for_platform(platform: Platform) -> frozenset[str]:
    """Return Sber-categories которые создают HA-platform."""
    return HA_PLATFORM_TO_CATEGORIES.get(platform, frozenset())


def ha_attribute_for_feature(feature: str) -> str | None:
    """Return имя HA-attribute для Sber-feature (если есть однозначный mapping)."""
    return FEATURE_TO_HA_ATTRIBUTE.get(feature)


# ---------------------------------------------------------------------------
# Sber image_set_type → category (substring match)
# ---------------------------------------------------------------------------
# Перенесено из `registry.IMAGE_TYPE_TO_CATEGORY` — single source of truth
# для определения категории по полю device.image_set_type.
IMAGE_TYPE_MAP: Final[dict[str, str]] = {
    # Lights — `dt_bulb` покрывает новый формат `dt_bulb_e27_m`, `dt_bulb_e14` и
    # т.п. (Sber 2025+ device type naming). `bulb` как fallback — для любых
    # будущих вариаций типа `smart_bulb`.
    "bulb_sber": "light",
    "dt_bulb": "light",
    "bulb": "light",
    "ledstrip_sber": "led_strip",
    "dt_ledstrip": "led_strip",
    "dt_led_strip": "led_strip",
    "led_strip": "led_strip",
    # Switches
    "dt_socket_sber": "socket",
    "dt_socket": "socket",
    "socket": "socket",
    "dt_relay": "relay",
    "relay": "relay",
    # Climate sensors
    "cat_sensor_temp_humidity": "sensor_temp",
    "dt_sensor_temp": "sensor_temp",
    "sensor_temp": "sensor_temp",
    # Binary sensors
    "dt_sensor_water_leak": "sensor_water_leak",
    "sensor_water_leak": "sensor_water_leak",
    "cat_sensor_door": "sensor_door",
    "dt_sensor_door": "sensor_door",
    "sensor_door": "sensor_door",
    "cat_sensor_motion": "sensor_pir",
    "dt_sensor_motion": "sensor_pir",
    "sensor_motion": "sensor_pir",
    "sensor_pir": "sensor_pir",
    "dt_sensor_smoke": "sensor_smoke",
    "sensor_smoke": "sensor_smoke",
    "dt_sensor_gas": "sensor_gas",
    "sensor_gas": "sensor_gas",
    # Scenario
    "scenario_button": "scenario_button",
    "button_scenario": "scenario_button",
    # Covers — более специфичные paterns идут первыми, чтобы `dt_curtain`
    # матчился как `curtain`, а не потенциально как что-то ещё.
    "dt_curtain": "curtain",
    "curtain": "curtain",
    "dt_gate": "gate",
    "gate": "gate",
    "dt_window_blind": "window_blind",
    "window_blind": "window_blind",
    "dt_valve": "valve",
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


def resolve_category(image_set_type: str | None) -> str | None:
    """Определить Sber-категорию по `image_set_type` устройства.

    Логика идентична `registry.resolve_category` (single source of truth):
    1. Сначала точное совпадение (надёжный путь).
    2. Substring-match (для совместимости с реальными вариантами вида
       "bulb_sber", "dt_socket_sber" и т.п.).

    Порядок IMAGE_TYPE_MAP важен — более специфичные паттерны должны идти
    раньше (Python 3.7+ dict preserves insertion order).

    Returns:
        Категория из ``CATEGORY_TO_HA_PLATFORMS`` или ``None`` если неизвестно.
    """
    if not image_set_type:
        return None
    if image_set_type in IMAGE_TYPE_MAP:
        return IMAGE_TYPE_MAP[image_set_type]
    for pattern, category in IMAGE_TYPE_MAP.items():
        if pattern in image_set_type:
            return category
    return None
