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
from ..spec.ha_mapping import resolve_category
from ._types import HaEntityData
from .category_specs import CATEGORY_SPECS, build_primary_entity
from .feature_specs import FEATURE_SPECS, is_applicable

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto


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

    # Build reported values dict: key → raw value
    reported: dict[str, Any] = {}
    for av in dto.reported_state:
        if av.key:
            reported[av.key] = av.value
    # Desired state overrides (user commands are authoritative for display)
    for av in dto.desired_state:
        if av.key:
            reported[av.key] = av.value

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
    convert HA values → Sber wire values, then wraps in typed AttributeValueDto.

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
