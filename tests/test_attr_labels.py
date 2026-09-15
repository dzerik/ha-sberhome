"""attr_label: подписи из translations/ + humanize-фолбэк."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant

from custom_components.sberhome import attr_labels
from custom_components.sberhome.attr_labels import (
    SUPPORTED_LANGS,
    _labels_for,
    async_load_attr_labels,
    attr_label,
    humanize,
)


@pytest.fixture(autouse=True)
def _loaded_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подписи загружены, как после настройки записи."""
    monkeypatch.setattr(attr_labels, "_labels", attr_labels._read_labels_file())


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


async def test_labels_read_from_disk_only_in_executor(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Файл подписей читается в executor, а не в event loop WS-обработчика.

    Проверка HA на блокирующие вызовы в тестах `Path.read_text` пропускает,
    поэтому поток чтения фиксируем сами.
    """
    loop_thread = threading.get_ident()
    read_threads: list[int] = []
    original_read_text = Path.read_text

    def _tracking_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self == attr_labels._LABELS_FILE:
            read_threads.append(threading.get_ident())
        return original_read_text(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "read_text", _tracking_read_text)
    monkeypatch.setattr(attr_labels, "_labels", None)  # запись ещё не настроена

    # Вызов из event loop до загрузки: без обращения к диску, humanize-фолбэк.
    assert attr_label("light_brightness", "ru") == "Light brightness"
    assert read_threads == []

    await async_load_attr_labels(hass)
    await async_load_attr_labels(hass)  # повторная загрузка файл не перечитывает

    assert len(read_threads) == 1
    assert read_threads[0] != loop_thread
    assert attr_label("light_brightness", "ru") == "Яркость"
