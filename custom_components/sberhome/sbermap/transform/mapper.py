"""Mapper: DeviceDto → list[HaEntityData].

Feature-Descriptor pattern: iterates DeviceDto.reported_state, creates
HaEntityData for each feature that has a FeatureSpec, plus a primary
composite entity from CategorySpec.

This replaces the 1255-line sber_to_ha.py with a ~80-line data-driven mapper.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_OFF, STATE_ON, Platform

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


__all__ = ["map_device_to_entities"]
