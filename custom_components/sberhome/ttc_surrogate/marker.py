"""Marker'ы для TTC (text-to-command) surrogate-сценариев.

Аналог `tts_surrogate.marker`, но для команд ассистенту (HEAD_DIALOG_COMMAND).
Discovery по имени сценария (list endpoint возвращает `name`, не `description`):

    Sber TTC surrogate (Мой дом) [home_id=c0o3edhu]

Префикс «TTC» отличает от TTS-surrogate того же дома (у обоих одинаковый
`[home_id=<8char>]`-substring).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..aiosber.dto.scenario import ScenarioDto

MARKER_PREFIX = "🤖 HA TTC surrogate (sberhome): home_id="
NAME_PREFIX = "Sber TTC surrogate"
NAME_HOME_ID_TEMPLATE = "[home_id={home_short}]"
HOME_ID_SHORT_LEN = 8


def home_id_short(home_id: str) -> str:
    return home_id[:HOME_ID_SHORT_LEN]


def build_marker(home_id: str) -> str:
    return f"{MARKER_PREFIX}{home_id}"


def build_surrogate_name(home_id: str, home_name: str) -> str:
    marker = NAME_HOME_ID_TEMPLATE.format(home_short=home_id_short(home_id))
    return f"{NAME_PREFIX} ({home_name}) {marker}"


def parse_marker(description: str | None) -> str | None:
    if not description:
        return None
    trimmed = description.strip()
    if not trimmed.startswith(MARKER_PREFIX):
        return None
    home_id = trimmed[len(MARKER_PREFIX) :].strip()
    return home_id or None


def match_surrogate(scenario: ScenarioDto, home_id: str) -> bool:
    """True если scenario — TTC-surrogate для home_id.

    NAME_PREFIX обязателен, чтобы не поймать TTS-surrogate того же дома.
    """
    short_marker = NAME_HOME_ID_TEMPLATE.format(home_short=home_id_short(home_id))
    if scenario.name and NAME_PREFIX in scenario.name and short_marker in scenario.name:
        return True
    parsed = parse_marker(scenario.description)
    return parsed == home_id
