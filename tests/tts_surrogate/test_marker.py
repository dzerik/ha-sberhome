"""Tests for TTS surrogate name + description markers."""

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.tts_surrogate.marker import (
    MARKER_PREFIX,
    build_marker,
    build_surrogate_name,
    home_id_short,
    match_surrogate,
    parse_marker,
)


def test_build_surrogate_name_includes_home_id_short():
    home_id = "c0o3edhu7jqgr5lbnks0"
    name = build_surrogate_name(home_id, "Мой дом")
    assert name.startswith("Sber TTS surrogate")
    assert "Мой дом" in name
    assert "[home_id=c0o3edhu]" in name


def test_home_id_short_takes_first_8_chars():
    assert home_id_short("c0o3edhu7jqgr5lbnks0") == "c0o3edhu"
    assert home_id_short("short") == "short"


def test_match_surrogate_by_name_substring():
    """Primary path: list endpoint возвращает name (без description) —
    discovery должен работать по name."""
    home_id = "c0o3edhu7jqgr5lbnks0"
    s = ScenarioDto(
        id="sc-1",
        name=build_surrogate_name(home_id, "Мой дом"),
        description=None,  # list endpoint не возвращает description
    )
    assert match_surrogate(s, home_id) is True
    # Тот же name, другой home_id → no match.
    assert match_surrogate(s, "d99zzzzz9zzzzzzzzzzz") is False


def test_match_surrogate_fallback_by_description():
    """Fallback: пользователь переименовал в Sber app — name больше не содержит
    marker, но description ещё есть. Match по description должен сработать."""
    s = ScenarioDto(
        id="sc-1",
        name="Renamed by user manually",
        description="🤖 HA TTS surrogate (sberhome): home_id=home-A",
    )
    assert match_surrogate(s, "home-A") is True
    assert match_surrogate(s, "home-B") is False


def test_build_marker_format():
    assert build_marker("abc-123") == "🤖 HA TTS surrogate (sberhome): home_id=abc-123"
    assert build_marker("abc-123").startswith(MARKER_PREFIX)


def test_parse_marker_happy():
    desc = "🤖 HA TTS surrogate (sberhome): home_id=home-uuid-1"
    assert parse_marker(desc) == "home-uuid-1"


def test_parse_marker_returns_none_on_no_match():
    assert parse_marker(None) is None
    assert parse_marker("") is None
    assert parse_marker("Just a description without marker") is None
    # Intent marker — другой namespace, не должен матчиться
    assert parse_marker("🤖 HA-managed (sberhome): slug=morning") is None


def test_parse_marker_tolerant_to_surrounding_whitespace():
    desc = "  🤖 HA TTS surrogate (sberhome): home_id=home-1  "
    assert parse_marker(desc) == "home-1"


def test_match_surrogate_no_match():
    """Сценарии без marker (ни в name, ни в description) не должны матчиться."""
    s = ScenarioDto(id="sc-3", name="Unrelated", description=None)
    assert match_surrogate(s, "home-A") is False
    s2 = ScenarioDto(id="sc-4", name="Random", description="Random description")
    assert match_surrogate(s2, "home-A") is False
