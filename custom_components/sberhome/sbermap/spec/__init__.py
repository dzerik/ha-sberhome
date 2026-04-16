"""Spec layer — single source of truth для категорий, features, HA-mappings."""

from __future__ import annotations

from ._generated import (
    ALL_CATEGORIES,
    CATEGORY_ALL_FEATURES,
    CATEGORY_FEATURES,
    CATEGORY_OBLIGATORY,
    FEATURE_ENUMS,
    FEATURE_RANGES,
    FEATURE_TYPES,
)
from .ha_mapping import (
    CATEGORY_TO_HA_PLATFORMS,
    FEATURE_TO_HA_ATTRIBUTE,
    HA_PLATFORM_TO_CATEGORIES,
    categories_for_platform,
    ha_attribute_for_feature,
    platforms_for_category,
)

__all__ = [
    "ALL_CATEGORIES",
    "CATEGORY_ALL_FEATURES",
    "CATEGORY_FEATURES",
    "CATEGORY_OBLIGATORY",
    "CATEGORY_TO_HA_PLATFORMS",
    "FEATURE_ENUMS",
    "FEATURE_RANGES",
    "FEATURE_TO_HA_ATTRIBUTE",
    "FEATURE_TYPES",
    "HA_PLATFORM_TO_CATEGORIES",
    "categories_for_platform",
    "ha_attribute_for_feature",
    "platforms_for_category",
]
