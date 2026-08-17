"""TTC surrogate markers + non-collision с TTS."""

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.ttc_surrogate.marker import (
    build_marker,
    build_surrogate_name,
    home_id_short,
    match_surrogate,
    parse_marker,
)
from custom_components.sberhome.tts_surrogate.marker import (
    build_surrogate_name as tts_name,
)
from custom_components.sberhome.tts_surrogate.marker import (
    match_surrogate as tts_match,
)


def test_build_name_includes_ttc_prefix_and_home():
    name = build_surrogate_name("c0o3edhu7jqgr5lbnks0", "Мой дом")
    assert name.startswith("Sber TTC surrogate")
    assert "Мой дом" in name
    assert "[home_id=c0o3edhu]" in name


def test_home_id_short():
    assert home_id_short("c0o3edhu7jqgr5lbnks0") == "c0o3edhu"


def test_match_by_name():
    home_id = "c0o3edhu7jqgr5lbnks0"
    s = ScenarioDto(id="sc-1", name=build_surrogate_name(home_id, "Мой дом"), description=None)
    assert match_surrogate(s, home_id) is True
    assert match_surrogate(s, "d99zzzzz9zzzzzzzzzzz") is False


def test_match_fallback_by_description():
    s = ScenarioDto(id="sc-1", name="Renamed", description=build_marker("home-A"))
    assert match_surrogate(s, "home-A") is True
    assert match_surrogate(s, "home-B") is False


def test_ttc_and_tts_do_not_cross_match():
    """Critical: TTS и TTC surrogate одного дома не должны матчить друг друга —
    у обоих одинаковый [home_id=…]-substring, различает только NAME_PREFIX."""
    home_id = "c0o3edhu7jqgr5lbnks0"
    ttc = ScenarioDto(id="ttc", name=build_surrogate_name(home_id, "Дом"), description=None)
    tts = ScenarioDto(id="tts", name=tts_name(home_id, "Дом"), description=None)
    # TTC-матчер берёт только TTC, TTS-матчер только TTS.
    assert match_surrogate(ttc, home_id) is True
    assert match_surrogate(tts, home_id) is False
    assert tts_match(tts, home_id) is True
    assert tts_match(ttc, home_id) is False


def test_parse_marker():
    assert parse_marker(build_marker("home-X")) == "home-X"
    assert parse_marker(None) is None
    assert parse_marker("нет маркера") is None
