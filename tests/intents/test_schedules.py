"""Regression contracts for opaque TIME, editor bounds and cloud write validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.sberhome.intents.encoder import decode_scenario, encode_scenario
from custom_components.sberhome.intents.schedules import (
    ReadOnlyScheduleError,
    ScheduleError,
    decode_time,
    editable_time,
    encode_time,
    parse_schedule,
)
from custom_components.sberhome.intents.spec import IntentSpec, IntentTrigger
from tests.intents.test_service import SAMPLE_SCENARIO, _build_service

RULE = (
    "DTSTART;TZID=Europe/Moscow:20300115T080000\n"
    "RRULE:FREQ=DAILY;WKST=MO;BYDAY=MO,TU,WE,TH,FR;BYHOUR=9;BYMINUTE=0;BYSECOND=0"
)
INVALID_RULES: list[Any] = [
    None,
    7,
    "",
    RULE + "\n",
    RULE + ";COUNT=3",
    RULE.replace("DAILY", "MONTHLY"),
    RULE.replace("WKST=MO;", "INTERVAL=2;"),
    RULE.replace("BYHOUR=9", "BYHOUR=9,18"),
    RULE.replace("BYHOUR=9", "BYHOUR=24"),
    RULE.replace("BYMINUTE=0", "BYMINUTE=60"),
    RULE.replace("BYSECOND=0", "BYSECOND=1"),
    RULE.replace("MO,TU,WE,TH,FR", "1MO"),
    RULE.replace("MO,TU,WE,TH,FR", "MO,MO"),
    RULE.replace("MO,TU,WE,TH,FR", "XX"),
    RULE.replace("Europe/Moscow", "Invalid/Zone"),
    RULE.replace("Europe/Moscow", "/etc/passwd"),
    RULE.replace("20300115", "20300230"),
    RULE.replace("080000", "250000"),
    RULE.replace("20300115", "00000115"),
    RULE.replace("\n", "\r\n"),
]


def _wire(condition: dict) -> dict:
    return {
        **deepcopy(SAMPLE_SCENARIO),
        "timezone": "Europe/Moscow",
        "steps": [
            {"tasks": deepcopy(SAMPLE_SCENARIO["steps"][0]["tasks"]), "condition": condition}
        ],
    }


def _first(wire: dict) -> dict:
    return wire["steps"][0]["condition"]["nested_conditions_data"]["conditions"][0]


@pytest.mark.parametrize("rule", INVALID_RULES)
def test_only_representable_rules_are_editable(rule):
    assert parse_schedule(rule) is None


def test_future_anchor_and_zone_are_recognized_without_defaults():
    parsed = parse_schedule(RULE, "Europe/Moscow")
    assert parsed is not None
    assert (parsed.start, parsed.timezone, parsed.hour, parsed.minute) == (
        "20300115T080000",
        "Europe/Moscow",
        9,
        0,
    )
    assert parsed.days == ("MO", "TU", "WE", "TH", "FR")
    assert parse_schedule(RULE, "UTC") is None
    assert parse_schedule(RULE.replace("Europe/Moscow", "UTC"), "UTC") is not None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"time_data": None},
        {"time_data": "future"},
        {"time_data": []},
        {"time_data": {}},
        {"time_data": {"rrule": None}},
        {"time_data": {"rrule": 7}},
        {"time_data": {"rrule": False}},
        {"time_data": {"rrule": {"future": [1, True]}}},
        {"time_data": {"execute_at": "2030-01-15T09:00:00+03:00", "rrule": ""}},
        {"time_data": {"execute_at": None, "rrule": RULE, "future": {"nested": [3]}}},
        {"time_data": {"rrule": RULE + ";COUNT=3"}},
        {"time_data": {"rrule": RULE}, "future": "metadata", "nested_conditions_data": 7},
    ],
)
def test_unrelated_save_preserves_entire_time_and_types(payload):
    original = {"type": "TIME", **deepcopy(payload)}
    snapshot = deepcopy(original)
    spec = decode_scenario(_wire(original))
    spec.name = "Новое имя"
    output = _first(encode_scenario(spec))
    assert output == snapshot
    assert spec.triggers[0].type == "time"
    assert original == snapshot
    output["new_field"] = True
    assert "new_field" not in spec.triggers[0].data["_raw"]
    assert editable_time(original) is None


@pytest.mark.parametrize("include_execute", [True, False])
def test_supported_time_edit_changes_only_rule_and_preserves_nullable_fields(include_execute):
    raw = {"type": "TIME", "time_data": {"rrule": RULE}, "device_data": None}
    if include_execute:
        raw["time_data"]["execute_at"] = None
    trigger = decode_time(raw)
    trigger.data["rrule"] = RULE.replace("BYHOUR=9", "BYHOUR=10")
    saved = encode_time(trigger, "Europe/Moscow")
    expected = deepcopy(raw)
    expected["time_data"]["rrule"] = trigger.data["rrule"]
    assert saved == expected
    assert raw["time_data"]["rrule"] == RULE


@pytest.mark.parametrize(
    "raw",
    [
        {"type": "TIME", "time_data": {"rrule": RULE + ";COUNT=3"}},
        {"type": "TIME", "time_data": {"execute_at": "2030-01-15T09:00:00Z"}},
        {"type": "TIME", "time_data": {"rrule": RULE, "metadata": "future"}},
        {"type": "TIME", "time_data": {"rrule": RULE}, "future": True},
    ],
)
def test_opaque_time_cannot_be_rewritten(raw):
    trigger = decode_time(raw)
    trigger.data["rrule"] = RULE.replace("BYHOUR=9", "BYHOUR=10")
    with pytest.raises(ReadOnlyScheduleError):
        encode_time(trigger)


def test_missing_null_and_boolean_number_changes_are_not_confused():
    trigger = decode_time({"type": "TIME", "time_data": {}})
    trigger.data["rrule"] = None
    with pytest.raises(ReadOnlyScheduleError):
        encode_time(trigger)
    trigger = decode_time({"type": "TIME", "time_data": {"rrule": False}})
    trigger.data["rrule"] = 0
    with pytest.raises(ReadOnlyScheduleError):
        encode_time(trigger)


@pytest.mark.parametrize(
    "rule", [RULE.replace("20300115", "20260115"), RULE.replace("Europe/Moscow", "UTC")]
)
def test_edit_cannot_replace_anchor_or_zone(rule):
    trigger = decode_time({"type": "TIME", "time_data": {"rrule": RULE}})
    trigger.data["rrule"] = rule
    with pytest.raises(ReadOnlyScheduleError):
        encode_time(trigger)


def test_invalid_edit_and_broken_original_are_rejected():
    trigger = decode_time({"type": "TIME", "time_data": {"rrule": RULE}})
    trigger.data["rrule"] = ""
    with pytest.raises(ScheduleError):
        encode_time(trigger)
    for raw in [None, [], {"type": "DEVICE"}]:
        with pytest.raises(ScheduleError):
            encode_time(IntentTrigger(type="time", data={"_raw": raw}))
    with pytest.raises(ScheduleError):
        encode_time(IntentTrigger(type="time", data={"rrule": ""}))
    assert encode_time(IntentTrigger(type="time", data={"rrule": RULE})) == {
        "type": "TIME",
        "time_data": {"execute_at": None, "rrule": RULE},
    }


def test_opaque_group_keeps_its_time_whole():
    condition = {
        "type": "CONDITIONS",
        "nested_conditions_data": {
            "relation": "AND",
            "conditions": [
                {"type": "TIME", "time_data": {"execute_at": "future", "future": [7]}},
                {"type": "FUTURE", "future": True},
            ],
        },
    }
    assert _first(encode_scenario(decode_scenario(_wire(condition)))) == condition


def test_removing_one_duplicate_time_does_not_remove_the_other():
    condition = {"type": "TIME", "time_data": {"rrule": RULE}}
    wire = _wire(
        {
            "type": "CONDITIONS",
            "nested_conditions_data": {
                "relation": "OR",
                "conditions": [deepcopy(condition), deepcopy(condition)],
            },
        }
    )
    spec = decode_scenario(wire)
    del spec.triggers[0]
    assert _first(encode_scenario(spec)) == condition
    assert (
        len(encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"]["conditions"])
        == 1
    )


@pytest.mark.parametrize("operation", ["create", "update"])
@pytest.mark.parametrize(
    "kind,key",
    [
        ("empty", "scenario_trigger_required"),
        ("invalid", "scenario_schedule_invalid"),
        ("opaque", "scenario_schedule_read_only"),
    ],
)
async def test_invalid_writes_are_translated_and_never_reach_cloud(operation, kind, key):
    service, coord = _build_service()
    spec = IntentSpec(name="Проверка")
    if kind == "invalid":
        spec.triggers = [IntentTrigger(type="time", data={"rrule": ""})]
    elif kind == "opaque":
        trigger = decode_time({"type": "TIME", "time_data": {"rrule": RULE + ";COUNT=3"}})
        trigger.data["rrule"] = RULE
        spec.triggers = [trigger]
    with pytest.raises(ServiceValidationError) as err:
        if operation == "create":
            await service.create_intent(spec)
        else:
            await service.update_intent("scenario", spec)
    assert err.value.translation_key == key
    coord.client.transport.post.assert_not_awaited()
    coord.client.transport.put.assert_not_awaited()
