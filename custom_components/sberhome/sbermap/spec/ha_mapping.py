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
    # Sber-owned колонки/портал (SberBoom Home/Mini, SberPortal). Через
    # Gateway REST доступны только hub/diag-атрибуты — media-control
    # для своих колонок идёт через VPS и не наш scope. Здесь делаем
    # минимум: онлайн/Zigbee/Matter readiness + LED-индикатор как light.
    "sber_speaker": (Platform.BINARY_SENSOR, Platform.LIGHT, Platform.SELECT),
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
    # Scenario — `cat_button` покрывает варианты `cat_button_m`/`_s`/`_l`,
    # используемые Сбером для виртуальных c2c-кнопок (Эмуляция присутствия,
    # триггер-кнопки сценариев из мобильного приложения).
    "scenario_button": "scenario_button",
    "button_scenario": "scenario_button",
    "cat_button": "scenario_button",
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
    # Sber-owned колонки: dt_boom_*, dt_portal_*, dt_box_*, dt_satellite_*.
    # Используется substring-match — покрывает варианты с цветовыми
    # суффиксами (`dt_boom_r2_dark_blue_s` и т.п.).
    "dt_boom": "sber_speaker",
    "dt_portal": "sber_speaker",
    "dt_box": "sber_speaker",
    "dt_satellite": "sber_speaker",
}


# ---------------------------------------------------------------------------
# Семантические keyword'ы категорий (token-fallback)
# ---------------------------------------------------------------------------
# Используется при miss'е phrase-substring как третий уровень fallback.
# Slug разбивается на токены по `_`, для каждого token-window (длинные
# первыми) ищется совпадение в обратном индексе `keyword → category`.
#
# Это автоматически покрывает новые префиксы Сбера (`cat_*`, `dt_*`,
# гипотетические `xyz_<тип>_v2`) без ручного обновления IMAGE_TYPE_MAP.
# Длинные phrase-keywords ("sensor_temp_humidity", "hvac_underfloor_heating")
# имеют приоритет над короткими — благодаря порядку перебора windows.
#
# Конфликты ключей запрещены: один keyword → одна категория. Проверяется
# на load (см. `_KEYWORD_TO_CATEGORY` ниже).
CATEGORY_KEYWORDS: Final[dict[str, frozenset[str]]] = {
    "light": frozenset({"light", "bulb"}),
    "led_strip": frozenset({"ledstrip", "led_strip"}),
    "socket": frozenset({"socket"}),
    "relay": frozenset({"relay"}),
    "sensor_temp": frozenset({"sensor_temp", "sensor_temp_humidity"}),
    "sensor_water_leak": frozenset({"sensor_water_leak"}),
    "sensor_door": frozenset({"sensor_door"}),
    "sensor_pir": frozenset({"sensor_motion", "sensor_pir"}),
    "sensor_smoke": frozenset({"sensor_smoke"}),
    "sensor_gas": frozenset({"sensor_gas"}),
    "scenario_button": frozenset({"scenario_button", "button_scenario"}),
    "curtain": frozenset({"curtain"}),
    "gate": frozenset({"gate"}),
    "window_blind": frozenset({"window_blind"}),
    "valve": frozenset({"valve"}),
    "hvac_ac": frozenset({"hvac_ac"}),
    "hvac_heater": frozenset({"hvac_heater"}),
    "hvac_radiator": frozenset({"hvac_radiator"}),
    "hvac_boiler": frozenset({"hvac_boiler"}),
    "hvac_underfloor_heating": frozenset({"hvac_underfloor", "hvac_underfloor_heating"}),
    "hvac_fan": frozenset({"hvac_fan"}),
    "hvac_humidifier": frozenset({"hvac_humidifier"}),
    "hvac_air_purifier": frozenset({"hvac_air_purifier"}),
    "kettle": frozenset({"kettle"}),
    "vacuum_cleaner": frozenset({"vacuum", "vacuum_cleaner"}),
    "tv": frozenset({"tv"}),
    "hub": frozenset({"hub"}),
    "intercom": frozenset({"intercom"}),
    "sber_speaker": frozenset({"boom", "portal", "satellite"}),
}


def _build_keyword_index() -> dict[str, str]:
    """Обратный индекс `keyword → category` с проверкой конфликтов."""
    idx: dict[str, str] = {}
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            prev = idx.get(kw)
            if prev is not None and prev != cat:
                raise ValueError(
                    f"CATEGORY_KEYWORDS conflict: keyword {kw!r} → {prev!r} vs {cat!r}"
                )
            idx[kw] = cat
    return idx


_KEYWORD_TO_CATEGORY: Final[dict[str, str]] = _build_keyword_index()

# IMAGE_TYPE_MAP-паттерны, отсортированные по длине (длинные → детерминизм).
# Раньше порядок зависел от insertion order словаря — хрупко.
_SORTED_IMAGE_PATTERNS: Final[tuple[str, ...]] = tuple(
    sorted(IMAGE_TYPE_MAP, key=len, reverse=True)
)


def _token_fallback(image_set_type: str) -> str | None:
    """Token-window поиск по `CATEGORY_KEYWORDS`.

    Разбивает slug на токены по `_` и проверяет multi-token windows от
    длинных к коротким — даёт приоритет специфичным phrase-keywords
    (`sensor_temp_humidity`) над generic (`sensor`).

    Examples:
        >>> _token_fallback("cat_ledstrip_m")    # ledstrip → led_strip
        'led_strip'
        >>> _token_fallback("xyz_bulb_pro_2026") # bulb → light
        'light'
        >>> _token_fallback("brand_new_device")  # нет keyword
        None
    """
    tokens = image_set_type.split("_")
    n = len(tokens)
    for size in range(n, 0, -1):
        for i in range(n - size + 1):
            window = "_".join(tokens[i : i + size])
            cat = _KEYWORD_TO_CATEGORY.get(window)
            if cat is not None:
                return cat
    return None


def resolve_category(
    image_set_type: str | None,
    *,
    slug: str | None = None,
) -> str | None:
    """Определить Sber-категорию устройства.

    Приоритет источников (от authoritative к heuristic):

    0. **`slug` из `full_categories[0].slug`** (если задан и известен) —
       стабильный машинный идентификатор от самого Sber. Используется,
       когда DeviceDto имеет заполненный `full_categories`. Это самый
       надёжный источник, не зависит от изменений именования
       `image_set_type` в новых прошивках.
    1. **Exact match** `image_set_type` ⇒ ``IMAGE_TYPE_MAP``.
    2. **Phrase substring** — pattern ⊂ image_set_type. Pattern'ы перебираются
       от длинных к коротким (детерминизм, не зависит от insertion order).
    3. **Token fallback** — slug разбивается на токены по `_`, multi-token
       windows ищутся в ``CATEGORY_KEYWORDS``. Автоматически покрывает
       новые префиксы Сбера (`cat_*`, `dt_*`, и т.п.).

    Args:
        image_set_type: значение поля `device.image_set_type` (например
            `cat_valve_l`). Может быть `None`.
        slug: значение `full_categories[0].slug` (например `valve`).
            Если совпадает с известной категорией из
            ``CATEGORY_TO_HA_PLATFORMS`` — возвращается напрямую.

    Returns:
        Категория из ``CATEGORY_TO_HA_PLATFORMS`` или ``None`` если неизвестно.
    """
    # Приоритет 0: явный slug из Sber API. Sber называет slug-и точно
    # так же, как ключи в CATEGORY_TO_HA_PLATFORMS, поэтому достаточно
    # проверить наличие в reference-map (защита от опечаток/новых
    # неизвестных категорий).
    #
    # Важно: SberBoom/SberPortal/SberBox приходят с `slug="default"`
    # (full_categories=[{"slug":"default", "name":"Разное"}]), а реальный
    # тип определяется только по `image_set_type` (`dt_boom_r2_*`).
    # Slug "default" нет в CATEGORY_TO_HA_PLATFORMS — попадаем в fallback
    # по image_set_type, который корректно классифицирует sber_speaker.
    if slug and slug in CATEGORY_TO_HA_PLATFORMS:
        return slug

    if not image_set_type:
        return None
    if image_set_type in IMAGE_TYPE_MAP:
        return IMAGE_TYPE_MAP[image_set_type]
    for pattern in _SORTED_IMAGE_PATTERNS:
        if pattern in image_set_type:
            return IMAGE_TYPE_MAP[pattern]
    return _token_fallback(image_set_type)


def resolve_device_category(dto: object) -> str | None:
    """Определить Sber-категорию для DeviceDto.

    Удобная обёртка над `resolve_category()`: достаёт `slug` из
    `dto.full_categories[0].slug` и `image_set_type` из `dto.image_set_type`,
    передаёт в основной resolver.

    Принимает `object` чтобы избежать circular import между sbermap и
    aiosber.dto.device. Реально ожидается DeviceDto.
    """
    return resolve_category(
        getattr(dto, "image_set_type", None),
        slug=getattr(dto, "primary_category_slug", None),
    )
