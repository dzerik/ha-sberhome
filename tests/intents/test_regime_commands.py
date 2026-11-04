"""Period-command editing preserves the observed cloud wire structure."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from custom_components.sberhome.intents.encoder import decode_scenario, encode_scenario
from custom_components.sberhome.intents.registry import get_action
from custom_components.sberhome.intents.spec import IntentAction, IntentSpec


@pytest.fixture
def regime_task():
    full = json.loads((Path(__file__).parent / "fixtures/scenario_full_example.json").read_text())
    task = next(t for step in full["steps"] for t in step["tasks"] if t["type"] == "REGIME_COMMAND")
    task["Id"] = "wrapper-id"
    task["future_metadata"] = {"preserve": True}
    task["regime_command_data"]["future_option"] = 42
    for i, nested in enumerate(task["regime_command_data"]["tasks"]):
        nested["Id"] = f"command-{i}"
        nested["start_delay"] = f"{i + 1}s"
        nested["head_dialog_command_task_data"]["device_id"] = f"speaker-{i}"
        nested["head_dialog_command_task_data"]["text"] = f"Command {i} "
    return task


def test_observed_regime_becomes_editable_and_round_trips(regime_task):
    source = deepcopy(regime_task)
    spec = decode_scenario({"name": "Periods", "steps": [{"tasks": [regime_task]}]})
    assert spec.is_ha_managed is True
    action = spec.actions[0]
    assert action.type == "regime_command"
    assert action.unknown is False
    assert [c["period"] for c in action.data["commands"]] == ["evening", "morning", "night"]
    assert encode_scenario(spec)["steps"][0]["tasks"] == [source]
    assert regime_task == source


def test_edit_and_remove_keep_each_commands_metadata(regime_task):
    original = deepcopy(regime_task)
    spec = decode_scenario({"name": "Periods", "steps": [{"tasks": [regime_task]}]})
    commands = spec.actions[0].data["commands"]
    commands.pop(1)
    commands[1].update(period="morning", device_id="other-speaker", text="New text")
    result = encode_scenario(spec)["steps"][0]["tasks"][0]
    expected = deepcopy(original)
    nested = expected["regime_command_data"]["tasks"]
    nested.pop(1)
    nested[1]["regime_condition"]["period"] = "morning"
    nested[1]["head_dialog_command_task_data"].update(device_id="other-speaker", text="New text")
    assert result == expected
    assert regime_task == original


def test_new_commands_use_unique_periods():
    commands = [
        {"period": "morning", "device_id": "speaker-1", "text": "First"},
        {"period": "evening", "device_id": "speaker-2", "text": "Second"},
    ]
    spec = IntentSpec(
        name="Periods", actions=[IntentAction(type="regime_command", data={"commands": commands})]
    )
    body = encode_scenario(spec)
    tasks = body["steps"][0]["tasks"][0]["regime_command_data"]["tasks"]
    assert [t["regime_condition"]["period"] for t in tasks] == ["morning", "evening"]
    assert all(t["regime_condition"]["daypart"] == "common" for t in tasks)
    assert all(t["regime_condition"]["calendar"] == "common" for t in tasks)
    assert all(t["regime_condition"]["rrule"] == "" for t in tasks)
    assert all(t["start_delay"] == "0s" for t in tasks)
    reopened = decode_scenario(body)
    assert [c["text"] for c in reopened.actions[0].data["commands"]] == ["First", "Second"]


@pytest.mark.parametrize(
    "change",
    [
        {"type": "FUTURE_TASK"},
        {
            "regime_condition": {
                "period": "future",
                "daypart": "common",
                "calendar": "common",
                "rrule": "",
            }
        },
        {
            "regime_condition": {
                "period": "morning",
                "daypart": "weekend",
                "calendar": "common",
                "rrule": "",
            }
        },
        {
            "regime_condition": {
                "period": "morning",
                "daypart": "common",
                "calendar": "holiday",
                "rrule": "",
            }
        },
        {
            "regime_condition": {
                "period": "morning",
                "daypart": "common",
                "calendar": "common",
                "rrule": "FREQ=DAILY",
            }
        },
        {"head_dialog_command_task_data": None},
    ],
)
def test_unknown_nested_variant_remains_lossless_read_only(regime_task, change):
    regime_task["regime_command_data"]["tasks"][0].update(change)
    spec = decode_scenario({"name": "Periods", "steps": [{"tasks": [regime_task]}]})
    assert spec.is_ha_managed is False
    assert spec.actions[0].unknown is True
    assert encode_scenario(spec)["steps"][0]["tasks"] == [regime_task]


@pytest.mark.parametrize(
    "commands",
    [
        None,
        [],
        "bad",
        [None],
        [{}],
        [{"period": "day", "device_id": "speaker", "text": "Hello"}],
        [{"period": "morning", "device_id": "", "text": "Hello"}],
        [{"period": "morning", "device_id": "speaker", "text": "  "}],
    ],
)
def test_invalid_edit_is_rejected_instead_of_dropping_action(commands):
    spec = IntentSpec(
        name="Periods", actions=[IntentAction(type="regime_command", data={"commands": commands})]
    )
    with pytest.raises(ValueError):
        encode_scenario(spec)


def test_registry_consumes_only_the_regime_task(regime_task):
    reg = get_action("regime_command")
    assert reg is not None
    other = {"type": "TRIGGER_NOTIFY_COMMAND"}
    decoded, remaining = reg.decode([other, regime_task, other])
    assert decoded.type == "regime_command"
    assert remaining == [other, other]
    assert reg.decode([other]) == (None, [other])


@pytest.mark.parametrize(
    "regime", [None, [], {}, {"tasks": []}, {"tasks": "bad"}, {"tasks": [None]}]
)
def test_malformed_regime_remains_raw(regime_task, regime):
    regime_task["regime_command_data"] = regime
    spec = decode_scenario({"name": "Unknown", "steps": [{"tasks": [regime_task]}]})
    assert spec.actions[0].unknown is True
    assert encode_scenario(spec)["steps"][0]["tasks"] == [regime_task]


def test_missing_period_remains_raw(regime_task):
    regime_task["regime_command_data"]["tasks"][0]["regime_condition"].pop("period")
    spec = decode_scenario({"name": "Unknown", "steps": [{"tasks": [regime_task]}]})
    assert spec.actions[0].unknown is True


def test_clear_wrapper_delay_keeps_nested_delays(regime_task):
    regime_task["start_delay"] = "15s"
    spec = decode_scenario({"name": "Periods", "steps": [{"tasks": [regime_task]}]})
    assert spec.actions[0].data["delay_seconds"] == 15
    spec.actions[0].data["delay_seconds"] = 0
    saved = encode_scenario(spec)["steps"][0]["tasks"][0]
    assert saved["start_delay"] == "0s"
    assert saved["regime_command_data"] == regime_task["regime_command_data"]


def test_duplicate_periods_are_rejected_before_cloud_silently_overwrites():
    command = {"period": "morning", "device_id": "speaker", "text": "First"}
    spec = IntentSpec(
        name="Periods",
        actions=[
            IntentAction(
                type="regime_command", data={"commands": [command, {**command, "text": "Second"}]}
            )
        ],
    )
    with pytest.raises(ValueError):
        encode_scenario(spec)


def test_duplicate_periods_decode_as_unknown(regime_task):
    nested = regime_task["regime_command_data"]["tasks"]
    nested[1]["regime_condition"]["period"] = nested[0]["regime_condition"]["period"]
    spec = decode_scenario({"name": "Unknown", "steps": [{"tasks": [regime_task]}]})
    assert spec.actions[0].unknown is True
    assert encode_scenario(spec)["steps"][0]["tasks"] == [regime_task]
