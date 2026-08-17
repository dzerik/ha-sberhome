"""attr_label: подписи из translations/ + humanize-фолбэк."""

import json
from pathlib import Path

from custom_components.sberhome.attr_labels import (
    SUPPORTED_LANGS,
    _labels_for,
    attr_label,
    humanize,
)

_TR = Path(__file__).parent.parent / "custom_components" / "sberhome" / "translations"


def test_labels_loaded_from_translations():
    assert attr_label("light_brightness", "ru") == "Яркость"
    assert attr_label("open_percentage", "ru") == "Процент открытия"
    assert attr_label("staros_LedBrightness", "ru") == "Яркость подсветки"


def test_localized_by_lang():
    assert attr_label("open_percentage", "en") == "Open percentage"
    assert attr_label("open_percentage", "uz") == "Ochilish foizi"
    assert attr_label("light_brightness", "kk") == "Жарықтық"
    assert attr_label("light_brightness", "en-US") == "Brightness"  # region → base


def test_fallback_to_ru_then_humanize():
    assert attr_label("some_new_attr", "en") == "Some new attr"


def test_humanize_camelcase_and_staros_prefix():
    assert humanize("staros_someCamelKey") == "Some Camel Key"
    assert humanize("LedBrightness") == "Led Brightness"


def test_all_langs_cover_same_keys():
    """Секция attr_labels во всех 5 языках покрывает те же ключи, что ru."""
    ru_keys = set(_labels_for("ru"))
    assert ru_keys, "ru attr_labels must be non-empty"
    for lang in SUPPORTED_LANGS:
        keys = set(json.loads((_TR / f"{lang}.json").read_text("utf-8")).get("attr_labels", {}))
        missing = ru_keys - keys
        assert not missing, f"{lang}.json attr_labels missing: {missing}"
        # непустые значения
        empty = [k for k, v in _labels_for(lang).items() if not str(v).strip()]
        assert not empty, f"{lang}.json attr_labels empty: {empty}"
