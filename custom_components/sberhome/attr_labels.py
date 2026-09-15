"""Человекочитаемые подписи writable-атрибутов для форм панели.

Форма `sberhome-attr-form` (редактор сценариев / debug / условие-триггер)
рисует поля по `device_write_schema`. Без подписи HA-панель показывала бы
сырой ключ (`light_brightness`, `open_percentage`, `staros_LedBrightness`).

Подписи 48 writable-атрибутов × 5 языков хранятся в `attr_labels.json`
(единое место для всех переводов; отдельный файл, т.к. hassfest не допускает
кастом-ключи в стандартных `strings.json`/`translations/*.json`).
`attr_label(key, lang)` берёт подпись на языке HA-инстанса (fallback
lang→ru→humanize), для незнакомых ключей — humanize-фолбэк (staros_-префикс
срезается, camelCase/snake_case → слова с заглавной).

Файл читается один раз в executor'е (:func:`async_load_attr_labels`, вызывается
при настройке записи) и дальше отдаётся из памяти: `attr_label` зовётся из
WS-обработчика прямо в event loop, и чтение файла там блокировало бы HA.
До загрузки подписей `attr_label` отдаёт humanize-фолбэк.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LABELS_FILE = Path(__file__).parent / "attr_labels.json"
_FALLBACK_LANG = "ru"
SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en", "be", "kk", "uz")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


_labels: dict[str, dict[str, str]] | None = None
"""Словарь {lang: {key: label}} из attr_labels.json; None — ещё не загружен."""


def _read_labels_file() -> dict[str, dict[str, str]]:
    """Прочитать attr_labels.json. Блокирующий I/O — только в executor'е."""
    try:
        data = json.loads(_LABELS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


async def async_load_attr_labels(hass: HomeAssistant) -> None:
    """Загрузить подписи в память, если они ещё не загружены.

    Args:
        hass: Экземпляр Home Assistant — чтение файла уходит в его executor.
    """
    global _labels
    if _labels is not None:
        return
    _labels = await hass.async_add_executor_job(_read_labels_file)


def _all_labels() -> dict[str, dict[str, str]]:
    """Весь словарь {lang: {key: label}} из памяти, без обращения к диску."""
    return _labels or {}


def _labels_for(lang: str) -> dict[str, str]:
    """Подписи для языка. Пустой dict если языка нет."""
    return dict(_all_labels().get(lang) or {})


def humanize(key: str) -> str:
    """Языконезависимый фолбэк: staros_-префикс срезается, camelCase/snake → слова."""
    k = key
    if k.startswith("staros_"):
        k = k[len("staros_") :]
    k = _CAMEL.sub(" ", k)
    k = k.replace("_", " ").strip()
    return k[:1].upper() + k[1:] if k else key


def attr_label(key: str, lang: str = "ru") -> str:
    """Подпись атрибута на языке ``lang`` (fallback lang→ru→humanize)."""
    code = (lang or "ru").split("-")[0]
    return _labels_for(code).get(key) or _labels_for(_FALLBACK_LANG).get(key) or humanize(key)
