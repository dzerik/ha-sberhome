"""Bidirectional mapper: DeviceDto ↔ HA entities/commands.

Read path (Sber → HA):
    map_device_to_entities(dto) → list[HaEntityData]

Write path (HA → Sber):
    build_command(device_id, on_off=True, light_brightness=200) → list[AttributeValueDto]
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_OFF, STATE_ON, Platform

from ...aiosber.dto import AttributeValueDto, ColorValue
from ...aiosber.dto.enums import AttributeValueType
from ..spec.ha_mapping import resolve_category
from ._types import HaEntityData
from .category_specs import CATEGORY_SPECS, build_primary_entity
from .feature_specs import FEATURE_SPECS, is_applicable

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto


# Epoch timestamps = "never initialized". Любой разумный last_sync будет
# лексикографически больше "1970-...", но строгая проверка надёжнее.
_EPOCH_PREFIXES: tuple[str, ...] = ("1970-01-01", "0001-01-01")


def _normalize_value(av: AttributeValueDto, declared_type: AttributeValueType | None) -> Any:
    """Прочитать значение с учётом задекларированного типа атрибута.

    Sber иногда присылает mismatch между `type` в API и задекларированным
    в attributes[] (Tuya-bridge, WS updates): например humidity declared
    FLOAT, но WS приходит с `{type: INTEGER, integer_value: 0,
    float_value: 40.0}` — реальное значение в float_value, а
    dispatcher `av.value` по type вернёт integer_value=0 (junk).

    Логика:
    - Declared FLOAT → читаем float_value напрямую, fallback на int.
    - Declared INTEGER → integer_value напрямую, fallback на float.
    - Иначе — стандартный dispatch через av.value.
    """
    if declared_type is AttributeValueType.FLOAT:
        if av.float_value is not None:
            return av.float_value
        if av.integer_value is not None:
            return float(av.integer_value)
        return None
    if declared_type is AttributeValueType.INTEGER:
        if av.integer_value is not None:
            return av.integer_value
        if av.float_value is not None:
            return int(av.float_value)
        return None
    return av.value


def _is_fresh_desired(desired_ts: str | None, reported_ts: str | None) -> bool:
    """True если desired state можно считать активной командой.

    Правила (ISO 8601 lexicographic comparison достаточно):
    - desired_ts отсутствует / None → НЕ свежий (sensor без команды).
    - desired_ts = epoch (1970/0001) → НЕ свежий (дефолт от Sber).
    - reported_ts отсутствует → desired свежий (старых данных нет).
    - desired_ts < reported_ts → НЕ свежий (команда уже применена).
    - иначе → свежий.
    """
    if not desired_ts:
        return False
    if desired_ts.startswith(_EPOCH_PREFIXES):
        return False
    if not reported_ts:
        return True
    return desired_ts >= reported_ts


def map_device_to_entities(dto: DeviceDto) -> list[HaEntityData]:
    """Map a single Sber DeviceDto → list of HA entities.

    Two-level dispatch:
    1. Primary entity from CategorySpec (composite: LIGHT, CLIMATE, COVER, etc.)
    2. Extra entities auto-discovered from reported_state via FeatureSpec
    """
    category = resolve_category(dto.image_set_type)
    if category is None:
        return []

    device_id = dto.id or ""
    name = dto.display_name or device_id

    # Build reported values dict: key → raw value.
    # Desired может перекрывать reported ТОЛЬКО если у desired есть свежий
    # last_sync (реальная команда в полёте). Для read-only features
    # (temperature/humidity/battery/online etc.) Sber возвращает в
    # desired_state junk: `last_sync=1970-01-01` + `value=range_min`
    # (напр. temperature=-40, humidity=0). Без этой проверки HA показывал
    # бы эти junk-значения вместо reported.
    # Задекларированный тип атрибута в device.attributes[].type —
    # источник истины. WS-updates иногда приходят с другим API type
    # (Tuya-bridged sensor: attr declared FLOAT, но WS может отдать
    # INTEGER integer_value="24" для 24°C). Без нормализации
    # TemperatureCodec думает "это Sber-native API ×10" и делит на 10 →
    # пользователь видит 2.4°C вместо 24°C.
    decl_types: dict[str, AttributeValueType | None] = {
        a.key: a.type for a in (dto.attributes or []) if a.key
    }

    reported: dict[str, Any] = {}
    reported_ts: dict[str, str | None] = {}
    for av in dto.reported_state:
        if av.key:
            reported[av.key] = _normalize_value(av, decl_types.get(av.key))
            reported_ts[av.key] = av.last_sync
    for av in dto.desired_state:
        if not av.key:
            continue
        if not _is_fresh_desired(av.last_sync, reported_ts.get(av.key)):
            continue
        reported[av.key] = _normalize_value(av, decl_types.get(av.key))

    cat_spec = CATEGORY_SPECS.get(category)
    consumed: frozenset[str] = cat_spec.consumed_features if cat_spec else frozenset()

    entities: list[HaEntityData] = []

    # 1. Primary entity (complex platform)
    if cat_spec and cat_spec.consumed_features:
        primary = build_primary_entity(reported, cat_spec, device_id, name, category)
        if primary is not None:
            entities.append(primary)

    # 2. Extra entities — auto-discovered from features
    for key, raw_value in reported.items():
        if key in consumed:
            continue
        spec = FEATURE_SPECS.get(key)
        if spec is None or spec.platform is None:
            continue
        if not is_applicable(spec, category):
            continue

        ha_value = spec.codec.to_ha(raw_value)
        suffix = key
        entity_name = f"{name} {suffix.replace('_', ' ').title()}"

        # Determine state based on platform
        if spec.platform is Platform.BINARY_SENSOR or spec.platform is Platform.SWITCH:
            state = STATE_ON if ha_value else STATE_OFF
        else:
            state = ha_value

        entities.append(
            HaEntityData(
                platform=spec.platform,
                unique_id=f"{device_id}_{suffix}",
                name=entity_name,
                state=state,
                device_class=spec.codec.device_class,
                unit_of_measurement=spec.codec.unit_of_measurement,
                state_class=spec.codec.state_class,
                entity_category=spec.entity_category or spec.codec.entity_category,
                icon=spec.icon or spec.codec.icon,
                state_attribute_key=key,
                sber_category=category,
                options=spec.options,
                min_value=spec.min_value,
                max_value=spec.max_value,
                step=spec.step,
                event_types=spec.event_types,
                command_value=spec.command_value,
                enabled_by_default=spec.enabled_by_default,
                suggested_display_precision=spec.codec.suggested_display_precision,
            )
        )

    return entities


# =============================================================================
# Reverse mapper: HA → Sber (write/command path)
# =============================================================================


def build_command(device_id: str, **features: Any) -> list[AttributeValueDto]:
    """Build list[AttributeValueDto] from HA-friendly kwargs.

    Generic bidirectional command builder: uses FEATURE_SPECS codecs to
    convert HA values → Sber API values, then wraps in typed AttributeValueDto.

    Usage:
        attrs = build_command("dev-1", on_off=True, light_brightness=200)
        await api.devices.set_state("dev-1", attrs)

    Replaces all per-platform build_*_command() functions.
    """
    attrs: list[AttributeValueDto] = []
    for key, ha_value in features.items():
        if ha_value is None:
            continue
        spec = FEATURE_SPECS.get(key)
        sber_value = spec.codec.to_sber(ha_value) if spec is not None else ha_value
        attrs.append(_to_attr(key, sber_value))
    return attrs


def _to_attr(key: str, value: Any) -> AttributeValueDto:
    """Auto-detect type and build AttributeValueDto."""
    if isinstance(value, bool):
        return AttributeValueDto.of_bool(key, value)
    if isinstance(value, int):
        return AttributeValueDto.of_int(key, value)
    if isinstance(value, float):
        return AttributeValueDto.of_float(key, value)
    if isinstance(value, str):
        return AttributeValueDto.of_enum(key, value)
    if isinstance(value, ColorValue):
        return AttributeValueDto.of_color(key, value)
    return AttributeValueDto.of_string(key, str(value))


__all__ = ["build_command", "map_device_to_entities"]
