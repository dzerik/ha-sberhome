"""Spec layer — HA ↔ Sber platform/category mapping helpers."""

from __future__ import annotations

from .ha_mapping import (
    CATEGORY_TO_HA_PLATFORMS,
    FEATURE_TO_HA_ATTRIBUTE,
    HA_PLATFORM_TO_CATEGORIES,
    categories_for_platform,
    ha_attribute_for_feature,
    platforms_for_category,
)

__all__ = [
    "CATEGORY_TO_HA_PLATFORMS",
    "FEATURE_TO_HA_ATTRIBUTE",
    "HA_PLATFORM_TO_CATEGORIES",
    "categories_for_platform",
    "ha_attribute_for_feature",
    "platforms_for_category",
]
