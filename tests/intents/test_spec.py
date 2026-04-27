"""IntentSpec / IntentAction / FieldSpec — round-trip serialization tests."""

from __future__ import annotations

from custom_components.sberhome.intents.spec import (
    FieldSpec,
    IntentAction,
    IntentSpec,
)


class TestIntentAction:
    def test_minimal_round_trip(self):
        a = IntentAction(type="ha_event_only")
        d = a.to_dict()
        assert d == {"type": "ha_event_only", "data": {}, "unknown": False}
        assert IntentAction.from_dict(d) == a

    def test_with_data_round_trip(self):
        a = IntentAction(
            type="tts",
            data={"phrase": "Привет", "device_ids": ["sb-1", "sb-2"]},
        )
        assert IntentAction.from_dict(a.to_dict()) == a

    def test_unknown_flag_preserved(self):
        a = IntentAction(type="regime_command", data={"foo": "bar"}, unknown=True)
        d = a.to_dict()
        assert d["unknown"] is True
        assert IntentAction.from_dict(d).unknown is True

    def test_from_dict_handles_missing_fields(self):
        """Forward-compat: legacy/garbled dicts."""
        a = IntentAction.from_dict({"type": "tts"})
        assert a.data == {}
        assert a.unknown is False


class TestIntentSpec:
    def test_minimal_round_trip(self):
        spec = IntentSpec(name="Утренний кофе")
        out = spec.to_dict()
        assert out["name"] == "Утренний кофе"
        assert out["enabled"] is True
        assert out["is_ha_managed"] is True
        assert out["actions"] == []
        assert out["phrases"] == []

    def test_full_round_trip(self):
        spec = IntentSpec(
            id="sc-42",
            name="Включи свет",
            phrases=["включи свет", "свет включи"],
            actions=[
                IntentAction(type="tts", data={"phrase": "Включаю!"}),
                IntentAction(type="ha_event_only"),
            ],
            enabled=True,
            description="Первый тест",
            last_fired_at="2026-04-27T13:12:04Z",
            is_ha_managed=True,
            raw_extras={"image": "..."},
        )
        round = IntentSpec.from_dict({**spec.to_dict(), "raw_extras": spec.raw_extras})
        # to_dict не выдаёт raw_extras (это internal storage), но from_dict умеет.
        assert round.id == spec.id
        assert round.actions == spec.actions
        assert round.last_fired_at == spec.last_fired_at
        assert round.raw_extras == {"image": "..."}

    def test_phrases_strip_empty(self):
        """Пустые фразы фильтруются — UI может прислать trailing empty input."""
        spec = IntentSpec.from_dict({"name": "X", "phrases": ["a", "  ", "", "b"]})
        assert spec.phrases == ["a", "b"]

    def test_unknown_action_type_kept(self):
        """Action с типом не-из-registry должен сохраняться (unknown flag
        выставляет encoder, но from_dict не валидирует — UI может
        отдать его обратно при save)."""
        spec = IntentSpec.from_dict(
            {"name": "X", "actions": [{"type": "future_action_type", "data": {}}]}
        )
        assert spec.actions[0].type == "future_action_type"


class TestFieldSpec:
    def test_minimal_to_dict(self):
        f = FieldSpec(key="phrase", type="text", label="Фраза")
        d = f.to_dict()
        assert d == {
            "key": "phrase",
            "type": "text",
            "label": "Фраза",
            "required": False,
            "multiple": False,
        }

    def test_full_to_dict(self):
        f = FieldSpec(
            key="device_ids",
            type="device_picker",
            label="Колонка",
            required=True,
            multiple=True,
            help_text="Выбери одну или несколько колонок",
            device_category=("sber_speaker",),
        )
        d = f.to_dict()
        assert d["help_text"] == "Выбери одну или несколько колонок"
        assert d["device_category"] == ["sber_speaker"]
        assert d["multiple"] is True

    def test_options_serialised_as_list(self):
        f = FieldSpec(
            key="severity",
            type="enum",
            label="Severity",
            options=("low", "medium", "high"),
        )
        assert f.to_dict()["options"] == ["low", "medium", "high"]

    def test_default_omitted_when_none(self):
        """default=None не пробрасываем — фронт сам решит."""
        f = FieldSpec(key="x", type="text", label="X")
        assert "default" not in f.to_dict()

    def test_default_passed_through(self):
        f = FieldSpec(key="x", type="number", label="X", default=42)
        assert f.to_dict()["default"] == 42
