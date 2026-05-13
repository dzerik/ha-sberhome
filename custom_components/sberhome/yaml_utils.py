"""Shared YAML helpers — slugify + другие чистые утилиты для intents/listeners."""

from __future__ import annotations

import re

_CYR_TO_LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def slugify(name: str) -> str:
    """Сгенерировать slug из name (Latin transliteration + lower).

    Базовая транслитерация Cyrillic → Latin, потом lowercase + замена
    всего non-alphanum на ``_``, ужатие повторяющихся ``_``.
    Fallback ``"intent"`` для пустой строки.
    """
    s = name.lower()
    s = "".join(_CYR_TO_LAT.get(c, c) for c in s)
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "intent"
