"""Encoder/Decoder tests — IntentSpec ↔ ScenarioDto wire format.

Live-fixtures из реального Sber Gateway response (см.
NEXT_STEPS / probe results).
"""

from __future__ import annotations

from custom_components.sberhome.intents.encoder import (
    DEFAULT_IMAGE,
    DEFAULT_TIMEZONE,
    decode_scenario,
    encode_scenario,
)
from custom_components.sberhome.intents.spec import IntentAction, IntentSpec

# ---------------------------------------------------------------------------
# Live fixtures from probe
# ---------------------------------------------------------------------------


# «HA API Test» сценарий созданный нами через REST POST на проде.
LIVE_HA_API_TEST = {
    "id": "69ef5b16c0372739c61341ae",
    "meta": {"created_at": "2026-04-27T12:48:22.290892Z"},
    "account_id": "28775",
    "image": "https://img.iot.sberdevices.ru/p/q100/e7/a4/abc.webp",
    "name": "HA API Test",
    "is_active": True,
    "timezone": "Europe/Moscow",
    "is_faulty": False,
    "home_id": "c0o3edhu7jqgr5lbnks0",
    "access_level": "OWNER",
    "steps": [
        {
            "tasks": [
                {
                    "type": "PRONOUNCE_COMMAND",
                    "pronounce_data": {
                        "device_ids": ["d7l4bbkelq0et912ro1g"],
                        "phrase": "Сценарий создан через API из Home Assistant",
                    },
                }
            ],
            "condition": {
                "type": "CONDITIONS",
                "nested_conditions_data": {
                    "conditions": [
                        {
                            "type": "PHRASES",
                            "phrases_data": {"phrases": ["проверка апи", "тест эпиай"]},
                        }
                    ],
                    "relation": "OR",
                },
            },
        }
    ],
}


# «Маркер один» — TRIGGER_NOTIFY_COMMAND action.
LIVE_MARKER_ODIN = {
    "id": "69ef56e968370bebf006ce7a",
    "name": "Маркер один ",
    "is_active": True,
    "timezone": "Europe/Moscow",
    "image": "https://img.iot.sberdevices.ru/p/q100/e7/a4/foo.webp",
    "steps": [
        {
            "tasks": [{"type": "TRIGGER_NOTIFY_COMMAND"}],
            "condition": {
                "type": "CONDITIONS",
                "nested_conditions_data": {
                    "conditions": [
                        {
                            "type": "PHRASES",
                            "phrases_data": {"phrases": ["Маркер один ", "Маркер один"]},
                        }
                    ],
                    "relation": "OR",
                },
            },
        }
    ],
}


# Сценарий с REGIME_COMMAND — тип который мы НЕ знаем (forward-compat test).
COMPLEX_SCENARIO_WITH_UNKNOWN = {
    "id": "abc-complex",
    "name": "Тёплый пол",
    "is_active": True,
    "timezone": "Europe/Moscow",
    "image": "https://img.iot.sberdevices.ru/...",
    "steps": [
        {
            "tasks": [
                {
                    "type": "REGIME_COMMAND",
                    "regime_command_data": {"some_field": "value"},
                }
            ],
            "condition": {
                "type": "CONDITIONS",
                "nested_conditions_data": {
                    "conditions": [{"type": "PHRASES", "phrases_data": {"phrases": ["согрей"]}}],
                    "relation": "OR",
                },
            },
        }
    ],
}


# ---------------------------------------------------------------------------
# Decode
# ---------------------------------------------------------------------------


class TestDecode:
    def test_ha_api_test_round_trip(self):
        spec = decode_scenario(LIVE_HA_API_TEST)
        assert spec.id == "69ef5b16c0372739c61341ae"
        assert spec.name == "HA API Test"
        assert spec.phrases == ["проверка апи", "тест эпиай"]
        assert len(spec.actions) == 1
        assert spec.actions[0].type == "tts"
        assert spec.actions[0].data == {
            "phrase": "Сценарий создан через API из Home Assistant",
            "device_ids": ["d7l4bbkelq0et912ro1g"],
        }
        assert spec.is_ha_managed is True
        # Forward-compat: незнакомые top-level поля сохранены.
        assert "meta" in spec.raw_extras
        assert spec.raw_extras["account_id"] == "28775"
        assert spec.raw_extras["image"].startswith("https://")
        assert "home_id" in spec.raw_extras

    def test_marker_odin_decodes_trigger_notify(self):
        spec = decode_scenario(LIVE_MARKER_ODIN)
        assert spec.name == "Маркер один"
        assert "Маркер один" in spec.phrases
        # Дубликат «Маркер один » / «Маркер один» — должен быть один в списке
        # фраз (после strip они одинаковые… ну нет, у одного trailing space).
        # Encoder сохраняет порядок без дедупа по trim'у — это expected.
        assert spec.actions[0].type == "trigger_notify"
        assert spec.is_ha_managed is True

    def test_unknown_action_marked(self):
        spec = decode_scenario(COMPLEX_SCENARIO_WITH_UNKNOWN)
        assert spec.is_ha_managed is False
        assert len(spec.actions) == 1
        assert spec.actions[0].unknown is True
        assert spec.actions[0].type == "REGIME_COMMAND"
        # raw payload сохранён в data для future encode'а назад
        assert spec.actions[0].data["raw"]["type"] == "REGIME_COMMAND"

    def test_empty_tasks_decodes_to_ha_event_only(self):
        scenario = {
            "id": "empty",
            "name": "X",
            "is_active": True,
            "steps": [
                {
                    "tasks": [],
                    "condition": {
                        "type": "PHRASES",
                        "phrases_data": {"phrases": ["икс"]},
                    },
                }
            ],
        }
        spec = decode_scenario(scenario)
        assert len(spec.actions) == 1
        assert spec.actions[0].type == "ha_event_only"
        # Phrases работает и для плоского condition без обёртки CONDITIONS.
        assert spec.phrases == ["икс"]


class TestDecodeMultipleActions:
    def test_tts_plus_trigger_notify(self):
        scenario = {
            "id": "multi",
            "name": "Multi",
            "is_active": True,
            "steps": [
                {
                    "tasks": [
                        {
                            "type": "PRONOUNCE_COMMAND",
                            "pronounce_data": {
                                "phrase": "ok",
                                "device_ids": ["s-1"],
                            },
                        },
                        {"type": "TRIGGER_NOTIFY_COMMAND"},
                    ],
                    "condition": {
                        "type": "PHRASES",
                        "phrases_data": {"phrases": ["multi"]},
                    },
                }
            ],
        }
        spec = decode_scenario(scenario)
        types = [a.type for a in spec.actions]
        assert "tts" in types
        assert "trigger_notify" in types
        assert spec.is_ha_managed is True

    def test_phrase_dedup_keeps_order(self):
        scenario = {
            "id": "dup",
            "name": "Dup",
            "is_active": True,
            "steps": [
                {
                    "tasks": [],
                    "condition": {
                        "type": "CONDITIONS",
                        "nested_conditions_data": {
                            "conditions": [
                                {
                                    "type": "PHRASES",
                                    "phrases_data": {"phrases": ["a", "b", "a"]},
                                }
                            ],
                            "relation": "OR",
                        },
                    },
                }
            ],
        }
        spec = decode_scenario(scenario)
        assert spec.phrases == ["a", "b"]


# ---------------------------------------------------------------------------
# Encode
# ---------------------------------------------------------------------------


class TestEncode:
    def test_minimal_intent_to_wire(self):
        spec = IntentSpec(
            name="Утро",
            phrases=["доброе утро"],
            actions=[IntentAction(type="ha_event_only")],
        )
        body = encode_scenario(spec)
        assert body["name"] == "Утро"
        assert body["is_active"] is True
        assert body["timezone"] == DEFAULT_TIMEZONE
        assert body["image"] == DEFAULT_IMAGE  # default
        # Один step с пустым tasks (ha_event_only).
        assert len(body["steps"]) == 1
        assert body["steps"][0]["tasks"] == []
        # Phrases в каноничной обёртке CONDITIONS/nested.
        cond = body["steps"][0]["condition"]
        assert cond["type"] == "CONDITIONS"
        nested_inner = cond["nested_conditions_data"]["conditions"][0]
        assert nested_inner["type"] == "PHRASES"
        assert nested_inner["phrases_data"]["phrases"] == ["доброе утро"]

    def test_round_trip_preserves_extras(self):
        """decode → encode → decode preserves все unknown поля."""
        spec_initial = decode_scenario(LIVE_HA_API_TEST)
        body = encode_scenario(spec_initial)
        # Должны увидеть оригинальный image (НЕ дефолтный) и home_id.
        assert body["image"] == "https://img.iot.sberdevices.ru/p/q100/e7/a4/abc.webp"
        assert body["home_id"] == "c0o3edhu7jqgr5lbnks0"
        assert body["account_id"] == "28775"
        # Round-trip: decode encoded body == initial spec по action/phrase.
        spec_round = decode_scenario(body)
        assert spec_round.name == spec_initial.name
        assert spec_round.phrases == spec_initial.phrases
        assert len(spec_round.actions) == len(spec_initial.actions)

    def test_unknown_action_re_emitted_into_tasks(self):
        """Unknown action из decoded — encoded обратно в `raw` task'ом.
        Это критично: если пользователь редактирует имя сценария, не
        трогая action'ы, мы не должны потерять REGIME_COMMAND."""
        spec = decode_scenario(COMPLEX_SCENARIO_WITH_UNKNOWN)
        # Меняем только имя.
        spec.name = "Тёплый пол (renamed)"
        body = encode_scenario(spec)
        tasks = body["steps"][0]["tasks"]
        assert len(tasks) == 1
        assert tasks[0]["type"] == "REGIME_COMMAND"
        assert tasks[0]["regime_command_data"]["some_field"] == "value"

    def test_encode_with_multiple_actions(self):
        spec = IntentSpec(
            name="Multi",
            phrases=["multi"],
            actions=[
                IntentAction(type="tts", data={"phrase": "ok", "device_ids": ["s-1"]}),
                IntentAction(type="trigger_notify"),
            ],
        )
        body = encode_scenario(spec)
        types = [t["type"] for t in body["steps"][0]["tasks"]]
        assert "PRONOUNCE_COMMAND" in types
        assert "TRIGGER_NOTIFY_COMMAND" in types

    def test_disabled_intent_encoded_as_inactive(self):
        spec = IntentSpec(name="Off", phrases=["x"], enabled=False)
        body = encode_scenario(spec)
        assert body["is_active"] is False
