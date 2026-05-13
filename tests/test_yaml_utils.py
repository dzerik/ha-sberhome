"""Tests for shared YAML utilities."""

from custom_components.sberhome.yaml_utils import slugify


def test_slugify_basic_cyrillic():
    assert slugify("Доброе утро") == "dobroe_utro"


def test_slugify_strips_special_chars():
    assert slugify("Test  -- 123!@#") == "test_123"


def test_slugify_empty_fallback():
    assert slugify("") == "intent"
