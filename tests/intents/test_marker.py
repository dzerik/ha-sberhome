"""Tests for intents.marker — HA-managed description-marker."""

from __future__ import annotations

import pytest

from custom_components.sberhome.intents.marker import (
    MARKER_PREFIX,
    WARNING_TEXT,
    build_description,
    is_ha_managed,
    parse_slug_from_description,
)


class TestBuildDescription:
    def test_minimal_no_user_desc(self):
        d = build_description("morning")
        assert d.startswith(MARKER_PREFIX)
        assert "slug=morning" in d
        assert WARNING_TEXT in d

    def test_with_user_desc(self):
        d = build_description("morning", "Утренний сценарий")
        assert "Утренний сценарий" in d
        assert "slug=morning" in d

    def test_user_desc_stripped(self):
        """Лишние пробелы юзер-описания убираются."""
        d = build_description("x", "   hi   ")
        assert "   hi" not in d
        assert "hi" in d

    def test_user_desc_blank_omitted(self):
        d_with = build_description("x", "")
        d_without = build_description("x")
        assert d_with == d_without


class TestIsHaManaged:
    def test_marker_present(self):
        d = build_description("morning")
        assert is_ha_managed(d) is True

    @pytest.mark.parametrize(
        "value",
        [
            "",
            None,
            "Просто описание от пользователя",
            "Мой сценарий\nс несколькими строками",
        ],
    )
    def test_marker_absent(self, value):
        assert is_ha_managed(value) is False


class TestParseSlug:
    def test_extracts_slug(self):
        d = build_description("morning")
        assert parse_slug_from_description(d) == "morning"

    def test_slug_with_underscores_and_dashes(self):
        d = build_description("home-assistant_morning_v2")
        assert parse_slug_from_description(d) == "home-assistant_morning_v2"

    def test_returns_none_when_no_marker(self):
        assert parse_slug_from_description("обычное описание") is None

    def test_returns_none_for_empty(self):
        assert parse_slug_from_description("") is None
        assert parse_slug_from_description(None) is None

    def test_tolerant_to_user_edits_after_marker(self):
        """Юзер дописал текст после маркера — slug всё равно находится."""
        d = build_description("evening") + "\n\nпользователь дописал что-то"
        assert parse_slug_from_description(d) == "evening"
