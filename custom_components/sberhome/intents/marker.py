"""HA-managed ownership marker для Sber-сценариев из YAML.

Поскольку Sber API не имеет meta-поля для маркировки «owned by
external integration», мы записываем маркер в `description` сценария.
Это видно пользователю в приложении «Салют!», что одновременно служит
предупреждением: не редактировать вручную, поскольку HA при reload
перезатрёт.

Формат маркера::

    🤖 HA-managed (sberhome): slug=<slug>
    ⚠ Не редактировать в приложении «Салют!» — будет перезаписано
    при перезагрузке Home Assistant.

    <user-description>

Где:
- `<slug>` — стабильный машинный идентификатор из YAML (имя секции).
- `<user-description>` — опциональное описание из YAML.

Slug извлекается обратно через `parse_slug_from_description()`,
который ищет в первой строке pattern `slug=...`.
"""

from __future__ import annotations

import re
from typing import Final

# Префикс, по которому identifying HA-managed сценарии. Эмодзи 🤖 —
# чтобы пользователю в Sber-app сразу было видно «это автоматическое».
MARKER_PREFIX: Final = "🤖 HA-managed (sberhome):"

# Предупреждение второй строкой.
WARNING_TEXT: Final = (
    "⚠ Не редактировать в приложении «Салют!» — будет перезаписано при перезагрузке Home Assistant."
)

# Pattern для извлечения slug из первой строки description.
# Берём всё, что после `slug=` до конца строки или whitespace.
_SLUG_RE: Final = re.compile(r"slug=([A-Za-z0-9_-]+)")


def build_description(slug: str, user_description: str = "") -> str:
    """Сформировать `description` для Sber-сценария с HA-managed маркером.

    Args:
        slug: уникальный идентификатор YAML-секции
            (например ``"morning"``).
        user_description: дополнительное описание из YAML
            (поле ``description:``). Пустая строка по умолчанию.

    Returns:
        Многострочный description: первой идёт строка-маркер, второй —
        предупреждение, дальше — пользовательский текст (если задан).
    """
    lines = [f"{MARKER_PREFIX} slug={slug}", WARNING_TEXT]
    if user_description.strip():
        lines.append("")
        lines.append(user_description.strip())
    return "\n".join(lines)


def is_ha_managed(description: str | None) -> bool:
    """True если description содержит HA-managed маркер."""
    if not description:
        return False
    return MARKER_PREFIX in description


def parse_slug_from_description(description: str | None) -> str | None:
    """Достать slug из HA-managed description. None если маркера нет.

    Toleranт к ручным правкам пользователя: если он добавил текст
    после маркера, slug всё равно найдётся (ищем regex'ом).
    """
    if not is_ha_managed(description):
        return None
    match = _SLUG_RE.search(description)
    return match.group(1) if match else None


__all__ = [
    "MARKER_PREFIX",
    "WARNING_TEXT",
    "build_description",
    "is_ha_managed",
    "parse_slug_from_description",
]
