"""attr_label: подписи из translations/ + humanize-фолбэк."""

from custom_components.sberhome.attr_labels import (
    SUPPORTED_LANGS,
    _labels_for,
    attr_label,
    humanize,
)


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
    """attr_labels.json: все 5 языков покрывают те же ключи, что ru, непусто."""
    ru_keys = set(_labels_for("ru"))
    assert ru_keys, "ru attr_labels must be non-empty"
    for lang in SUPPORTED_LANGS:
        labels = _labels_for(lang)
        missing = ru_keys - set(labels)
        assert not missing, f"{lang} attr_labels missing: {missing}"
        empty = [k for k, v in labels.items() if not str(v).strip()]
        assert not empty, f"{lang} attr_labels empty: {empty}"
