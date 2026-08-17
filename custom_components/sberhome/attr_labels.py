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
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

_LABELS_FILE = Path(__file__).parent / "attr_labels.json"
_FALLBACK_LANG = "ru"
SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en", "be", "kk", "uz")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


@cache
def _all_labels() -> dict[str, dict[str, str]]:
    """Весь словарь {lang: {key: label}} из attr_labels.json (кэш)."""
    try:
        return json.loads(_LABELS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


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
