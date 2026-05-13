"""Tests for intents.yaml_loader — YAML schema + parse → IntentSpec."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.sberhome.intents.yaml_loader import (
    INTENTS_SCHEMA,
    load_intents_from_config,
)

VALID_MINIMAL = [
    {
        "name": "Доброе утро",
        "phrases": ["доброе утро"],
        "actions": [{"type": "ha_event_only"}],
    }
]

VALID_FULL = [
    {
        "slug": "evening",
        "name": "Спокойной ночи",
        "phrases": ["спокойной ночи", "выключи всё"],
        "enabled": False,
        "description": "Вечерний сценарий",
        "actions": [
            {
                "type": "tts",
                "phrase": "Сладких снов",
                "device_ids": ["speaker-1"],
            },
            {
                "type": "device_command",
                "device_id": "light-1",
                "attributes": [
                    {"key": "on_off", "type": "BOOL", "bool_value": False},
                ],
            },
            {"type": "ha_event_only"},
        ],
    }
]


class TestSchemaValidation:
    def test_valid_minimal(self):
        result = INTENTS_SCHEMA(VALID_MINIMAL)
        assert len(result) == 1
        assert result[0]["enabled"] is True  # default

    def test_valid_full(self):
        result = INTENTS_SCHEMA(VALID_FULL)
        assert result[0]["slug"] == "evening"
        assert result[0]["enabled"] is False

    def test_missing_name(self):
        with pytest.raises(vol.Invalid):
            INTENTS_SCHEMA([{"phrases": ["x"], "actions": [{"type": "ha_event_only"}]}])

    def test_empty_phrases(self):
        with pytest.raises(vol.Invalid):
            INTENTS_SCHEMA([{"name": "X", "phrases": [], "actions": [{"type": "ha_event_only"}]}])

    def test_empty_actions(self):
        with pytest.raises(vol.Invalid):
            INTENTS_SCHEMA([{"name": "X", "phrases": ["x"], "actions": []}])

    def test_unknown_action_type(self):
        with pytest.raises(vol.Invalid):
            INTENTS_SCHEMA(
                [
                    {
                        "name": "X",
                        "phrases": ["x"],
                        "actions": [{"type": "regime_command"}],
                    }
                ]
            )

    def test_tts_requires_phrase(self):
        with pytest.raises(vol.Invalid):
            INTENTS_SCHEMA(
                [
                    {
                        "name": "X",
                        "phrases": ["x"],
                        "actions": [
                            {"type": "tts", "device_ids": ["spk"]},  # no phrase
                        ],
                    }
                ]
            )

    def test_device_command_requires_attributes(self):
        with pytest.raises(vol.Invalid):
            INTENTS_SCHEMA(
                [
                    {
                        "name": "X",
                        "phrases": ["x"],
                        "actions": [
                            {"type": "device_command", "device_id": "d", "attributes": []},
                        ],
                    }
                ]
            )

    def test_slug_invalid_format(self):
        """Slug должен быть lowercase alphanum + _/-."""
        with pytest.raises(vol.Invalid):
            INTENTS_SCHEMA(
                [
                    {
                        "slug": "BAD UPPER!",
                        "name": "X",
                        "phrases": ["x"],
                        "actions": [{"type": "ha_event_only"}],
                    }
                ]
            )


class TestLoadIntents:
    def test_minimal_parses(self):
        validated = INTENTS_SCHEMA(VALID_MINIMAL)
        specs = load_intents_from_config(validated)
        assert len(specs) == 1
        assert specs[0].name == "Доброе утро"
        assert specs[0].phrases == ["доброе утро"]
        assert specs[0].actions[0].type == "ha_event_only"

    def test_slug_autogen_from_cyrillic(self):
        """Cyrillic name → transliterated lowercase slug."""
        validated = INTENTS_SCHEMA(VALID_MINIMAL)
        specs = load_intents_from_config(validated)
        slug = specs[0].raw_extras["yaml_slug"]
        # "Доброе утро" → "dobroe_utro"
        assert slug == "dobroe_utro"

    def test_slug_explicit_preserved(self):
        validated = INTENTS_SCHEMA(VALID_FULL)
        specs = load_intents_from_config(validated)
        assert specs[0].raw_extras["yaml_slug"] == "evening"

    def test_duplicate_slug_raises(self):
        """Два intent'а с одинаковым slug → ValueError."""
        data = [
            {
                "slug": "x",
                "name": "A",
                "phrases": ["a"],
                "actions": [{"type": "ha_event_only"}],
            },
            {
                "slug": "x",
                "name": "B",
                "phrases": ["b"],
                "actions": [{"type": "ha_event_only"}],
            },
        ]
        validated = INTENTS_SCHEMA(data)
        with pytest.raises(ValueError, match="duplicate slug"):
            load_intents_from_config(validated)

    def test_actions_data_preserved(self):
        validated = INTENTS_SCHEMA(VALID_FULL)
        specs = load_intents_from_config(validated)
        tts_action = specs[0].actions[0]
        assert tts_action.type == "tts"
        assert tts_action.data["phrase"] == "Сладких снов"
        assert tts_action.data["device_ids"] == ["speaker-1"]

        dc_action = specs[0].actions[1]
        assert dc_action.type == "device_command"
        assert dc_action.data["device_id"] == "light-1"
        assert dc_action.data["attributes"][0]["key"] == "on_off"

    def test_description_default_empty(self):
        validated = INTENTS_SCHEMA(VALID_MINIMAL)
        specs = load_intents_from_config(validated)
        assert specs[0].description == ""

    def test_enabled_default_true(self):
        validated = INTENTS_SCHEMA(VALID_MINIMAL)
        specs = load_intents_from_config(validated)
        assert specs[0].enabled is True
