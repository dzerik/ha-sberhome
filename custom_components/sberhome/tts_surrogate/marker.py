"""Marker'ы для surrogate-сценариев.

Discovery идёт по **имени сценария** — Sber list endpoint
``GET /scenario/v2/scenario`` гарантированно возвращает поле ``name``,
но НЕ возвращает ``description`` (только в полном GET по id). Поэтому
основной marker встроен в ``name``::

    Sber TTS surrogate (Мой дом) [home_id=c0o3edhu]

где ``home_id=c0o3edhu`` — короткий префикс UUID дома (8 chars,
достаточно для уникальности в рамках одного аккаунта).

Description-marker оставлен как secondary signal для случаев когда
имя было вручную переименовано пользователем в Sber app — fallback
по описанию через `parse_marker_desc`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..aiosber.dto.scenario import ScenarioDto

# Описание (secondary marker, full GET only)
MARKER_PREFIX = "🤖 HA TTS surrogate (sberhome): home_id="

# Name marker — substring который должен быть в name для discovery.
NAME_PREFIX = "Sber TTS surrogate"
# Метка home_id в name: `[home_id=<8-char-prefix>]`.
NAME_HOME_ID_TEMPLATE = "[home_id={home_short}]"
# Длина короткого префикса home_id в name. UUID Sber'а base32-like,
# 8 chars дают 32^8 = 1T комбинаций — достаточно для уникальности
# в рамках одного аккаунта (где обычно 1-3 дома).
HOME_ID_SHORT_LEN = 8


def home_id_short(home_id: str) -> str:
    """Короткий префикс home_id для встраивания в name сценария."""
    return home_id[:HOME_ID_SHORT_LEN]


def build_marker(home_id: str) -> str:
    """Description-marker (secondary signal). Полный home_id в description."""
    return f"{MARKER_PREFIX}{home_id}"


def build_surrogate_name(home_id: str, home_name: str) -> str:
    """Имя surrogate-сценария с встроенным home_id-меткой.

    Формат: ``Sber TTS surrogate (<home_name>) [home_id=<8-char-prefix>]``.
    Discovery в `match_surrogate` ищет по substring ``[home_id=<8-char>]``.
    """
    marker = NAME_HOME_ID_TEMPLATE.format(home_short=home_id_short(home_id))
    return f"{NAME_PREFIX} ({home_name}) {marker}"


def parse_marker(description: str | None) -> str | None:
    """Извлечь home_id из description, либо None если marker не найден.

    Tolerant к ведущим/завершающим пробелам.
    """
    if not description:
        return None
    trimmed = description.strip()
    if not trimmed.startswith(MARKER_PREFIX):
        return None
    home_id = trimmed[len(MARKER_PREFIX) :].strip()
    return home_id or None


def match_surrogate(scenario: ScenarioDto, home_id: str) -> bool:
    """True если scenario — surrogate для указанного home_id.

    Primary: substring `[home_id=<8-char>]` в name (работает с list endpoint
    который не возвращает description).
    Fallback: marker в description (если был full GET с description).
    """
    short_marker = NAME_HOME_ID_TEMPLATE.format(home_short=home_id_short(home_id))
    if scenario.name and short_marker in scenario.name:
        return True
    # Fallback по description (на случай если juzер переименовал scenario
    # в Sber app, но description остался).
    parsed = parse_marker(scenario.description)
    return parsed == home_id
