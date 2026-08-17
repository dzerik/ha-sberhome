"""Человекочитаемые подписи writable-атрибутов для форм панели.

Форма `sberhome-attr-form` (редактор сценариев / debug / условие-триггер)
рисует поля по `device_write_schema`. Без подписи HA-панель показывала бы
сырой ключ (`light_brightness`, `open_percentage`, `staros_LedBrightness`).

Подписи хранятся в стандартных файлах локализации
`translations/{ru,en,be,kk,uz}.json` под ключом ``attr_labels`` (единое место
для всех переводов). `attr_label(key, lang)` берёт подпись на языке HA-инстанса
(fallback lang→ru→humanize), для незнакомых ключей — humanize-фолбэк
(staros_-префикс срезается, camelCase/snake_case → слова с заглавной).
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

_TRANSLATIONS = Path(__file__).parent / "translations"
_FALLBACK_LANG = "ru"
SUPPORTED_LANGS: tuple[str, ...] = ("ru", "en", "be", "kk", "uz")

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


@cache
def _labels_for(lang: str) -> dict[str, str]:
    """`attr_labels`-секция файла перевода языка (кэш). Пустой dict если нет."""
    path = _TRANSLATIONS / f"{lang}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return dict(data.get("attr_labels") or {})


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
    return (
        _labels_for(code).get(key) or _labels_for(_FALLBACK_LANG).get(key) or humanize(key)
    )
