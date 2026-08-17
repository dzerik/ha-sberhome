"""Триггеры (time/device/unknown) + 3 новых action (speaker_text /
scenario_status / sms) — decode/encode round-trip.

Fixture `fixtures/scenario_full_example.json` — реальный «Все что есть»
сценарий со всеми типами триггеров и задач (server-valid снимок).
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.sberhome.intents.encoder import (
    _build_condition,
    _collect_triggers,
    decode_scenario,
    encode_scenario,
)
from custom_components.sberhome.intents.registry import get_action
from custom_components.sberhome.intents.spec import (
    IntentSpec,
    IntentTrigger,
)

_FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "scenario_full_example.json").read_text(encoding="utf-8")
)


def _fixture_condition() -> dict:
    return _FIXTURE["steps"][0]["condition"]


# ---------------------------------------------------------------------------
# IntentTrigger serialization
# ---------------------------------------------------------------------------


class TestIntentTriggerSerde:
    def test_round_trip(self):
        t = IntentTrigger(type="time", data={"rrule": "RRULE:FREQ=DAILY"})
        assert IntentTrigger.from_dict(t.to_dict()) == t

    def test_unknown_flag(self):
        t = IntentTrigger(type="unknown", data={"raw": {"type": "X"}}, unknown=True)
        d = t.to_dict()
        assert d["unknown"] is True
        assert IntentTrigger.from_dict(d) == t

    def test_from_dict_defaults(self):
        t = IntentTrigger.from_dict({})
        assert t.type == "unknown"
        assert t.data == {}
        assert t.unknown is False

    def test_spec_carries_triggers(self):
        spec = IntentSpec(
            name="x",
            triggers=[IntentTrigger(type="time", data={"rrule": "R"})],
        )
        got = IntentSpec.from_dict(spec.to_dict())
        assert got.triggers == spec.triggers

    def test_spec_from_dict_missing_triggers(self):
        got = IntentSpec.from_dict({"name": "x", "phrases": [], "actions": []})
        assert got.triggers == []


# ---------------------------------------------------------------------------
# _collect_triggers — decode from wire
# ---------------------------------------------------------------------------


class TestCollectTriggers:
    def test_fixture_top_level_types(self):
        triggers = _collect_triggers(_fixture_condition())
        # top-OR: TIME, CONDITIONS(nested-AND→unknown), PHRASES(skip)
        assert [t.type for t in triggers] == ["time", "unknown"]

    def test_fixture_time_rrule_verbatim(self):
        triggers = _collect_triggers(_fixture_condition())
        time_t = triggers[0]
        assert "FREQ=DAILY" in time_t.data["rrule"]
        assert time_t.data["rrule"].startswith("DTSTART;TZID=Europe/Moscow")

    def test_unknown_raw_verbatim(self):
        cond = _fixture_condition()
        triggers = _collect_triggers(cond)
        original_conditions = cond["nested_conditions_data"]["conditions"]
        middle = original_conditions[1]  # the nested CONDITIONS block
        assert triggers[1].data["raw"] == middle

    def test_flat_single_device_condition(self):
        # condition без обёртки — плоский single DEVICE
        cond = {
            "type": "DEVICE",
            "device_data": {
                "device_id": "dev1",
                "categories_slugs": ["sensor_water_leak"],
                "condition": {
                    "state": {"key": "water_leak_state", "type": "BOOL"},
                    "condition": "EQUAL",
                    "delay": "0s",
                },
                "parent_id": "parent1",
            },
        }
        triggers = _collect_triggers(cond)
        assert len(triggers) == 1
        t = triggers[0]
        assert t.type == "device"
        assert t.data["device_id"] == "dev1"
        assert t.data["operator"] == "EQUAL"
        assert t.data["parent_id"] == "parent1"
        assert t.data["categories_slugs"] == ["sensor_water_leak"]
        assert t.data["attribute"] == {"key": "water_leak_state", "type": "BOOL"}

    def test_non_dict(self):
        assert _collect_triggers(None) == []
        assert _collect_triggers("nope") == []


# ---------------------------------------------------------------------------
# _build_condition — encode to wire
# ---------------------------------------------------------------------------


class TestBuildCondition:
    def test_empty(self):
        c = _build_condition([], [])
        assert c["nested_conditions_data"]["conditions"] == []
        assert c["nested_conditions_data"]["relation"] == "OR"

    def test_phrases_only(self):
        c = _build_condition(["hi"], [])
        conds = c["nested_conditions_data"]["conditions"]
        assert [x["type"] for x in conds] == ["PHRASES"]
        assert conds[0]["phrases_data"]["phrases"] == ["hi"]

    def test_order_triggers_then_phrases(self):
        triggers = [
            IntentTrigger(type="time", data={"rrule": "RRULE:FREQ=DAILY"}),
            IntentTrigger(type="unknown", data={"raw": {"type": "CONDITIONS"}}, unknown=True),
        ]
        c = _build_condition(["hi"], triggers)
        conds = c["nested_conditions_data"]["conditions"]
        assert [x["type"] for x in conds] == ["TIME", "CONDITIONS", "PHRASES"]

    def test_time_encode(self):
        c = _build_condition([], [IntentTrigger(type="time", data={"rrule": "R"})])
        t = c["nested_conditions_data"]["conditions"][0]
        assert t == {"type": "TIME", "time_data": {"execute_at": None, "rrule": "R"}}

    def test_empty_time_dropped(self):
        c = _build_condition([], [IntentTrigger(type="time", data={"rrule": "  "})])
        assert c["nested_conditions_data"]["conditions"] == []

    def test_unknown_verbatim(self):
        raw = {"type": "CHECK_DEVICE", "foo": [1, 2, 3]}
        c = _build_condition([], [IntentTrigger(type="unknown", data={"raw": raw}, unknown=True)])
        assert c["nested_conditions_data"]["conditions"][0] == raw

    def test_device_encode(self):
        t = IntentTrigger(
            type="device",
            data={
                "device_id": "dev1",
                "categories_slugs": ["sensor_water_leak"],
                "attribute": {"key": "water_leak_state", "type": "BOOL"},
                "operator": "EQUAL",
                "delay_seconds": 5,
                "parent_id": "parent1",
            },
        )
        c = _build_condition([], [t])
        enc = c["nested_conditions_data"]["conditions"][0]
        assert enc["type"] == "DEVICE"
        dd = enc["device_data"]
        assert dd["device_id"] == "dev1"
        assert dd["parent_id"] == "parent1"
        assert dd["categories_slugs"] == ["sensor_water_leak"]
        assert dd["condition"]["state"] == {"key": "water_leak_state", "type": "BOOL"}
        assert dd["condition"]["condition"] == "EQUAL"
        assert dd["condition"]["delay"] == "5s"

    def test_device_no_id_dropped(self):
        t = IntentTrigger(type="device", data={"device_id": ""})
        c = _build_condition([], [t])
        assert c["nested_conditions_data"]["conditions"] == []

    def test_device_no_parent_omits_key(self):
        t = IntentTrigger(type="device", data={"device_id": "dev1", "attribute": {}})
        c = _build_condition([], [t])
        dd = c["nested_conditions_data"]["conditions"][0]["device_data"]
        assert "parent_id" not in dd

    def test_device_delay_string_no_crash(self):
        # regression: delay_seconds='60s' (строка) не должна ронять encode
        t = IntentTrigger(type="device", data={"device_id": "dev1", "delay_seconds": "60s"})
        c = _build_condition([], [t])
        dd = c["nested_conditions_data"]["conditions"][0]["device_data"]
        assert dd["condition"]["delay"] == "60s"

    def test_device_delay_garbage_defaults_zero(self):
        t = IntentTrigger(type="device", data={"device_id": "dev1", "delay_seconds": "junk"})
        c = _build_condition([], [t])
        dd = c["nested_conditions_data"]["conditions"][0]["device_data"]
        assert dd["condition"]["delay"] == "0s"


# ---------------------------------------------------------------------------
# Round-trip lossless for triggers
# ---------------------------------------------------------------------------


class TestTriggerRoundTrip:
    def test_device_lossless(self):
        # decode → re-encode DEVICE, ключевые поля сохранены
        cond = {
            "type": "DEVICE",
            "device_data": {
                "device_id": "dev1",
                "categories_slugs": ["sensor_water_leak"],
                "condition": {
                    "state": {"key": "k", "type": "BOOL", "bool_value": True},
                    "condition": "EQUAL",
                    "delay": "0s",
                },
                "parent_id": "parent1",
            },
        }
        triggers = _collect_triggers(cond)
        c = _build_condition([], triggers)
        got = c["nested_conditions_data"]["conditions"][0]
        assert got["device_data"]["device_id"] == "dev1"
        assert got["device_data"]["condition"]["state"] == {
            "key": "k",
            "type": "BOOL",
            "bool_value": True,
        }

    def test_unknown_byte_identical(self):
        cond = _fixture_condition()
        triggers = _collect_triggers(cond)
        rebuilt = _build_condition(["Все что есть", "Охоз"], triggers)
        # unknown-блок должен вернуться байт-в-байт
        original = cond["nested_conditions_data"]["conditions"][1]
        assert rebuilt["nested_conditions_data"]["conditions"][1] == original

    def test_full_scenario_decode(self):
        spec = decode_scenario(_FIXTURE)
        assert spec.phrases == ["Все что есть", "Охоз"]
        assert [t.type for t in spec.triggers] == ["time", "unknown"]

    def test_full_scenario_reencode_condition_order(self):
        spec = decode_scenario(_FIXTURE)
        body = encode_scenario(spec)
        conds = body["steps"][0]["condition"]["nested_conditions_data"]["conditions"]
        assert [c["type"] for c in conds] == ["TIME", "CONDITIONS", "PHRASES"]

    def test_nested_phrase_not_duplicated(self):
        # regression: PHRASES внутри вложенной AND-группы не должна
        # дублироваться и создавать голую OR-ветку (обход DEVICE-условия).
        scenario = {
            "id": "x",
            "name": "n",
            "is_active": True,
            "steps": [
                {
                    "tasks": [],
                    "condition": {
                        "type": "CONDITIONS",
                        "nested_conditions_data": {
                            "relation": "OR",
                            "conditions": [
                                {
                                    "type": "CONDITIONS",
                                    "nested_conditions_data": {
                                        "relation": "AND",
                                        "conditions": [
                                            {
                                                "type": "PHRASES",
                                                "phrases_data": {"phrases": ["включи свет"]},
                                            },
                                            {"type": "DEVICE", "device_data": {"device_id": "d1"}},
                                        ],
                                    },
                                }
                            ],
                        },
                    },
                }
            ],
        }
        spec = decode_scenario(scenario)
        # фраза НЕ вытянута наверх (она внутри unknown-группы)
        assert spec.phrases == []
        assert [t.type for t in spec.triggers] == ["unknown"]
        body = encode_scenario(spec)
        conds = body["steps"][0]["condition"]["nested_conditions_data"]["conditions"]
        # только исходная AND-группа, без добавленной голой PHRASES-ветки
        assert len(conds) == 1
        assert conds[0]["type"] == "CONDITIONS"

    def test_top_level_phrase_plus_device(self):
        # phrase на верхней OR-плоскости рядом с device — обе собраны,
        # без дублирования
        scenario = {
            "id": "x",
            "name": "n",
            "is_active": True,
            "steps": [
                {
                    "tasks": [],
                    "condition": {
                        "type": "CONDITIONS",
                        "nested_conditions_data": {
                            "relation": "OR",
                            "conditions": [
                                {"type": "PHRASES", "phrases_data": {"phrases": ["привет"]}},
                                {
                                    "type": "DEVICE",
                                    "device_data": {
                                        "device_id": "d1",
                                        "condition": {"state": {}, "condition": "EQUAL"},
                                    },
                                },
                            ],
                        },
                    },
                }
            ],
        }
        spec = decode_scenario(scenario)
        assert spec.phrases == ["привет"]
        assert [t.type for t in spec.triggers] == ["device"]

    def test_backward_compat_phrases_only(self):
        # старый PHRASES-only сценарий → triggers пуст, phrases целы
        scenario = {
            "id": "x",
            "name": "old",
            "is_active": True,
            "steps": [
                {
                    "tasks": [],
                    "condition": {
                        "type": "PHRASES",
                        "phrases_data": {"phrases": ["привет"]},
                    },
                }
            ],
        }
        spec = decode_scenario(scenario)
        assert spec.triggers == []
        assert spec.phrases == ["привет"]


# ---------------------------------------------------------------------------
# 3 новых action: speaker_text / scenario_status / sms
# ---------------------------------------------------------------------------


class TestSpeakerText:
    def test_round_trip(self):
        reg = get_action("speaker_text")
        data = {"device_id": "spk1", "text": "Включи радио", "period": "evening"}
        tasks = reg.encode(data)
        assert tasks[0]["type"] == "REGIME_COMMAND"
        got, leftover = reg.decode(tasks)
        assert leftover == []
        assert got.data == data

    def test_default_period(self):
        reg = get_action("speaker_text")
        tasks = reg.encode({"device_id": "spk1", "text": "hi"})
        hd = tasks[0]["regime_command_data"]["tasks"][0]
        assert hd["regime_condition"]["period"] == "common"

    def test_empty_drops(self):
        reg = get_action("speaker_text")
        assert reg.encode({"device_id": "", "text": "hi"}) == []
        assert reg.encode({"device_id": "s", "text": ""}) == []

    def test_regime_with_rrule_not_consumed(self):
        # одиночный head_dialog, но с rrule → не воспроизводим → unknown
        reg = get_action("speaker_text")
        task = {
            "type": "REGIME_COMMAND",
            "regime_command_data": {
                "tasks": [
                    {
                        "type": "HEAD_DIALOG_COMMAND",
                        "head_dialog_command_task_data": {
                            "device_id": "s1",
                            "text": "hi",
                            "content_id": "",
                            "cinema": "",
                            "action_type": "",
                            "content": "",
                        },
                        "regime_condition": {
                            "daypart": "common",
                            "period": "morning",
                            "calendar": "common",
                            "rrule": "FREQ=DAILY",
                        },
                    }
                ]
            },
        }
        got, leftover = reg.decode([task])
        assert got is None
        assert leftover == [task]

    def test_regime_with_content_not_consumed(self):
        reg = get_action("speaker_text")
        task = {
            "type": "REGIME_COMMAND",
            "regime_command_data": {
                "tasks": [
                    {
                        "type": "HEAD_DIALOG_COMMAND",
                        "head_dialog_command_task_data": {
                            "device_id": "s1",
                            "text": "hi",
                            "content_id": "film42",
                            "cinema": "",
                            "action_type": "",
                            "content": "",
                        },
                        "regime_condition": {
                            "daypart": "common",
                            "period": "common",
                            "calendar": "common",
                            "rrule": "",
                        },
                    }
                ]
            },
        }
        got, leftover = reg.decode([task])
        assert got is None
        assert leftover == [task]

    def test_multiperiod_not_consumed(self):
        # реальный REGIME из fixture с 3 head_dialog → НЕ speaker_text
        regime = next(t for t in _FIXTURE["steps"][0]["tasks"] if t["type"] == "REGIME_COMMAND")
        reg = get_action("speaker_text")
        got, leftover = reg.decode([regime])
        assert got is None
        assert leftover == [regime]


class TestScenarioStatus:
    def test_round_trip(self):
        reg = get_action("scenario_status")
        data = {"scenario_id": "abc123", "active": False}
        tasks = reg.encode(data)
        assert tasks[0]["scenario_set_active_task_data"] == data
        got, leftover = reg.decode(tasks)
        assert leftover == []
        assert got.data == data

    def test_empty_id_drops(self):
        reg = get_action("scenario_status")
        assert reg.encode({"scenario_id": "", "active": True}) == []

    def test_decode_fixture(self):
        task = next(t for t in _FIXTURE["steps"][0]["tasks"] if t["type"] == "SCENARIO_SET_ACTIVE")
        reg = get_action("scenario_status")
        got, leftover = reg.decode([task])
        assert got.data["scenario_id"] == "69efa35911f9dae5a1fc5025"
        assert got.data["active"] is False


class TestSms:
    def test_lossless_raw(self):
        reg = get_action("sms")
        task = next(t for t in _FIXTURE["steps"][0]["tasks"] if t["type"] == "SEND_SMS_COMMAND")
        got, leftover = reg.decode([task])
        assert leftover == []
        tasks = reg.encode(got.data)
        assert tasks[0]["send_sms_command_task_data"] == task["send_sms_command_task_data"]

    def test_encode_default_form(self):
        reg = get_action("sms")
        tasks = reg.encode({})
        assert tasks[0]["send_sms_command_task_data"] == {
            "scenario_id": "",
            "scenario_name": "",
            "trigger_device_id": "",
        }


class TestSchemaDict:
    def test_new_actions_present(self):
        from custom_components.sberhome.intents.registry import schema_dict

        types = {a["type"] for a in schema_dict()}
        assert {"speaker_text", "scenario_status", "sms"} <= types

    def test_speaker_text_fields(self):
        from custom_components.sberhome.intents.registry import schema_dict

        st = next(a for a in schema_dict() if a["type"] == "speaker_text")
        keys = {f["key"] for f in st["fields"]}
        assert keys == {"device_id", "text", "period"}
        period = next(f for f in st["fields"] if f["key"] == "period")
        assert period["type"] == "enum"
        assert "common" in period["options"]
