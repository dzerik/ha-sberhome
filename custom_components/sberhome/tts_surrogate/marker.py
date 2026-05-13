"""Description-marker для surrogate-сценариев.

Формат::

    🤖 HA TTS surrogate (sberhome): home_id=<uuid>

Кладётся в ``ScenarioDto.description``. Тот же ownership-pattern что
у intents (`🤖 HA-managed (sberhome): slug=...`), но другой namespace —
не пересекается.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..aiosber.dto.scenario import ScenarioDto

MARKER_PREFIX = "🤖 HA TTS surrogate (sberhome): home_id="


def build_marker(home_id: str) -> str:
    """Создать marker-строку для description-поля сценария."""
    return f"{MARKER_PREFIX}{home_id}"


def parse_marker(description: str | None) -> str | None:
    """Извлечь home_id из description, либо None если marker не найден.

    Tolerant к ведущим/завершающим пробелам. Точный prefix-match — intent
    marker (`🤖 HA-managed (sberhome): ...`) не совпадает.
    """
    if not description:
        return None
    trimmed = description.strip()
    if not trimmed.startswith(MARKER_PREFIX):
        return None
    home_id = trimmed[len(MARKER_PREFIX) :].strip()
    return home_id or None


def match_surrogate(scenario: ScenarioDto, home_id: str) -> bool:
    """True если scenario — surrogate для указанного home_id."""
    parsed = parse_marker(scenario.description)
    return parsed == home_id
