"""Nested trigger editing must preserve both Boolean logic and per-node wire data."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from custom_components.sberhome.intents.encoder import decode_scenario, encode_scenario
from custom_components.sberhome.intents.spec import IntentSpec, IntentTrigger


@pytest.fixture
def group():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/scenario_full_example.json").read_text()
    )
    raw = fixture["steps"][0]["condition"]["nested_conditions_data"]["conditions"][1]
    raw["future"] = {"keep": True}
    for i, c in enumerate(raw["nested_conditions_data"]["conditions"]):
        c["Id"] = f"node-{i}"
    return raw


def scenario(raw):
    return {
        "name": "Условия",
        "steps": [
            {
                "condition": {
                    "type": "CONDITIONS",
                    "nested_conditions_data": {"relation": "OR", "conditions": [raw]},
                },
                "tasks": [],
            }
        ],
    }


def test_group_becomes_editable_and_roundtrips(group):
    original = deepcopy(group)
    spec = decode_scenario(scenario(group))
    node = spec.triggers[0]
    assert node.type == "group" and not node.unknown
    assert [c["type"] for c in node.data["conditions"]] == [
        "device",
        "check_device",
        "check_scenario",
    ]
    assert encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"][
        "conditions"
    ] == [original]
    assert group == original


def test_edit_relation_leaf_and_delete_preserves_metadata(group):
    spec = decode_scenario(scenario(group))
    original = deepcopy(group)
    node = spec.triggers[0]
    node.data["relation"] = "AND"
    children = node.data["conditions"]
    children.pop(1)
    children[1]["data"]["status"] = "pending"
    children[1]["data"]["scenario_id"] = "other-scenario"
    expected = deepcopy(original)
    expected["nested_conditions_data"]["relation"] = "AND"
    expected["nested_conditions_data"]["conditions"].pop(1)
    expected["nested_conditions_data"]["conditions"][1]["check_scenario_conditions_data"][
        "scenario_id"
    ] = "other-scenario"
    assert encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"][
        "conditions"
    ] == [expected]
    assert group == original


def test_root_and_does_not_promote_phrases():
    raw = {
        "type": "CONDITIONS",
        "nested_conditions_data": {
            "relation": "AND",
            "conditions": [
                {"type": "PHRASES", "phrases_data": {"phrases": ["проверка"]}},
                {
                    "type": "CHECK_SCENARIO",
                    "check_scenario_conditions_data": {
                        "scenario_id": "scenario",
                        "status": "pending",
                    },
                },
            ],
        },
    }
    spec = decode_scenario({"name": "И", "steps": [{"condition": raw, "tasks": []}]})
    assert spec.phrases == []
    assert len(spec.triggers) == 1 and spec.triggers[0].unknown
    assert encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"][
        "conditions"
    ] == [raw]


def test_unknown_child_survives_edit(group):
    children = group["nested_conditions_data"]["conditions"]
    children.insert(1, {"type": "FUTURE_CONDITION", "opaque": [1, 2, 3]})
    spec = decode_scenario(scenario(group))
    node = spec.triggers[0]
    assert node.type == "group" and node.data["conditions"][1]["unknown"]
    node.data["conditions"][0]["data"]["attribute"]["bool_value"] = False
    raw = encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"]["conditions"][0]
    assert raw["nested_conditions_data"]["conditions"][1] == children[1]
    assert (
        raw["nested_conditions_data"]["conditions"][0]["device_data"]["condition"]["state"][
            "bool_value"
        ]
        is False
    )


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"relation": "X", "conditions": []},
        {"relation": "AND", "conditions": []},
        {"relation": "AND", "conditions": [{"type": "check_device", "data": {"device_id": ""}}]},
        {
            "relation": "OR",
            "conditions": [{"type": "check_scenario", "data": {"scenario_id": "s", "status": ""}}],
        },
        {"relation": "OR", "conditions": [{"type": "not_registered", "data": {}}]},
    ],
)
def test_invalid_group_rejected(data):
    with pytest.raises(ValueError):
        encode_scenario(IntentSpec(name="И", triggers=[IntentTrigger(type="group", data=data)]))


@pytest.mark.parametrize(
    "nested",
    [
        None,
        {},
        {"relation": "X", "conditions": []},
        {"relation": "AND", "conditions": []},
        {"relation": "AND", "conditions": [None]},
    ],
)
def test_malformed_group_stays_raw(group, nested):
    group["nested_conditions_data"] = nested
    spec = decode_scenario(scenario(group))
    assert spec.triggers[0].unknown
    assert encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"][
        "conditions"
    ] == [group]


def test_edit_state_keeps_future_attribute_fields(group):
    state = group["nested_conditions_data"]["conditions"][0]["device_data"]["condition"]["state"]
    state["future"] = {"keep": True}
    spec = decode_scenario(scenario(group))
    spec.triggers[0].data["conditions"][0]["data"]["attribute"] = {
        "key": "water_leak_state",
        "type": "BOOL",
        "bool_value": False,
    }
    saved = encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"]["conditions"][
        0
    ]
    got = saved["nested_conditions_data"]["conditions"][0]["device_data"]["condition"]["state"]
    assert got == {**state, "bool_value": False}


@pytest.mark.parametrize("size", [8, 65])
def test_large_tree_is_preserved_read_only_and_invalid_new_tree_rejected(group, size):
    if size == 8:
        for _ in range(9):
            group = {
                "type": "CONDITIONS",
                "nested_conditions_data": {"relation": "OR", "conditions": [group]},
            }
    else:
        group["nested_conditions_data"]["conditions"] *= size
    spec = decode_scenario(scenario(group))
    assert spec.triggers[0].unknown
    assert encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"][
        "conditions"
    ] == [group]
    leaf = {"type": "device", "data": {"device_id": "d", "attribute": {"key": "k", "type": "BOOL"}}}
    if size == 8:
        for _ in range(10):
            leaf = {"type": "group", "data": {"relation": "OR", "conditions": [leaf]}}
    else:
        leaf = {"type": "group", "data": {"relation": "OR", "conditions": [leaf] * 65}}
    with pytest.raises(ValueError):
        encode_scenario(IntentSpec(name="Размер", triggers=[IntentTrigger.from_dict(leaf)]))


@pytest.mark.parametrize("change", [{"type": []}, {"type": "FUTURE"}, {"key": ""}])
def test_uneditable_attribute_remains_raw(group, change):
    group["nested_conditions_data"]["conditions"][0]["device_data"]["condition"]["state"].update(
        change
    )
    spec = decode_scenario(scenario(group))
    assert spec.triggers[0].unknown
    assert encode_scenario(spec)["steps"][0]["condition"]["nested_conditions_data"][
        "conditions"
    ] == [group]


def test_new_device_leaf_and_check_scenario_roundtrip():
    group = IntentTrigger(
        type="group",
        data={
            "relation": "AND",
            "conditions": [
                {
                    "type": "device",
                    "data": {
                        "device_id": "sensor",
                        "attribute": {"key": "k", "type": "BOOL", "bool_value": True},
                        "operator": "EQUAL",
                        "delay_seconds": 5,
                    },
                },
                {"type": "check_scenario", "data": {"scenario_id": "other", "status": "pending"}},
            ],
        },
    )
    encoded = encode_scenario(IntentSpec(name="Новые", triggers=[group]))
    reopened = decode_scenario(encoded).triggers[0]
    assert reopened.type == "group" and reopened.data["relation"] == "AND"
    assert reopened.data["conditions"][0]["data"]["delay_seconds"] == 5


def test_or_alternatives_can_contain_and_group(group):
    raw = {
        "type": "CONDITIONS",
        "nested_conditions_data": {
            "relation": "OR",
            "conditions": [group, group["nested_conditions_data"]["conditions"][0]],
        },
    }
    node = decode_scenario(scenario(raw)).triggers[0]
    assert node.type == "group" and node.data["relation"] == "OR"
    assert node.data["conditions"][0]["type"] == "group"
    assert encode_scenario(IntentSpec(name="Или", triggers=[node]))["steps"][0]["condition"][
        "nested_conditions_data"
    ]["conditions"] == [raw]


@pytest.mark.parametrize(
    "relation,kinds",
    [
        ("AND", ["check_device"]),
        ("AND", ["device", "group"]),
        ("AND", ["device", "device"]),
        ("OR", ["device", "check_device"]),
    ],
)
def test_reject_cloud_unsupported_group_shapes(group, relation, kinds):
    source = decode_scenario(scenario(group)).triggers[0]
    samples = {c["type"]: c for c in source.data["conditions"]}
    samples["group"] = source.to_dict()
    node = IntentTrigger(
        type="group",
        data={"relation": relation, "conditions": [deepcopy(samples[k]) for k in kinds]},
    )
    with pytest.raises(ValueError):
        encode_scenario(IntentSpec(name="Состав", triggers=[node]))
