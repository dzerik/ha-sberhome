"""Tests for TTS surrogate description marker."""

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.tts_surrogate.marker import (
    MARKER_PREFIX,
    build_marker,
    match_surrogate,
    parse_marker,
)


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


def test_match_surrogate():
    s1 = ScenarioDto(
        id="sc-1",
        description="🤖 HA TTS surrogate (sberhome): home_id=home-A",
    )
    s2 = ScenarioDto(
        id="sc-2",
        description="🤖 HA TTS surrogate (sberhome): home_id=home-B",
    )
    s3 = ScenarioDto(id="sc-3", description=None)
    s4 = ScenarioDto(id="sc-4", description="Random description")
    assert match_surrogate(s1, "home-A") is True
    assert match_surrogate(s1, "home-B") is False
    assert match_surrogate(s2, "home-B") is True
    assert match_surrogate(s3, "home-A") is False
    assert match_surrogate(s4, "home-A") is False
