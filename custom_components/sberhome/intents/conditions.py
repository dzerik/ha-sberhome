"""Lossless condition-tree mapping; no HA or network dependencies."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .spec import IntentTrigger

MAX_CONDITION_DEPTH = 8
MAX_CONDITION_NODES = 64
OPERATORS = frozenset(
    {"EQUAL", "NOT_EQUAL", "GREATER", "LESS", "GREATER_OR_EQUAL", "LESS_OR_EQUAL"}
)
STATE_TYPES = frozenset({"BOOL", "INTEGER", "FLOAT", "ENUM", "COLOR", "STRING"})
_DEVICE_KEYS = {"device": "device_data", "check_device": "check_device_conditions_data"}


def parse_delay_seconds(value: Any) -> int:
    """Parse the shared Sber duration representation without exposing wire details."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(float(value.strip().rstrip("s"))))
        except ValueError:
            return 0
    return 0


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _valid_device(data: dict[str, Any]) -> bool:
    state = data.get("attribute")
    return (
        _text(data.get("device_id"))
        and isinstance(state, dict)
        and _text(state.get("key"))
        and _text(state.get("type"))
        and state["type"] in STATE_TYPES
        and isinstance(data.get("operator", "EQUAL"), str)
        and data.get("operator", "EQUAL") in OPERATORS
    )


def valid_group_shape(relation: str, children: list[dict[str, Any]]) -> bool:
    """The cloud models AND as one device event plus checks, OR as alternatives."""
    kinds = [child.get("type") for child in children if not child.get("unknown")]
    if relation == "AND":
        return kinds.count("device") == 1 and all(
            kind in ("device", "check_device", "check_scenario", "unknown") for kind in kinds
        )
    return relation == "OR" and all(kind in ("device", "group", "unknown") for kind in kinds)


def _unknown(raw: dict[str, Any]) -> IntentTrigger:
    return IntentTrigger(type="unknown", data={"raw": deepcopy(raw)}, unknown=True)


def decode_condition(raw: dict[str, Any]) -> IntentTrigger:
    """Decode supported branches; preserve any unsupported branch whole and unchanged."""
    try:
        return _decode(raw, 0, [0])
    except ValueError:
        return _unknown(raw)


def _decode(raw: dict[str, Any], depth: int, count: list[int]) -> IntentTrigger:
    count[0] += 1
    if depth > MAX_CONDITION_DEPTH or count[0] > MAX_CONDITION_NODES:
        raise ValueError("Condition tree is too large")
    kind = raw.get("type")
    if kind == "CONDITIONS":
        nested = raw.get("nested_conditions_data")
        if not isinstance(nested, dict):
            return _unknown(raw)
        children = nested.get("conditions")
        if (
            nested.get("relation") not in ("AND", "OR")
            or not isinstance(children, list)
            or not children
            or not all(isinstance(c, dict) for c in children)
        ):
            return _unknown(raw)
        decoded = [_decode(c, depth + 1, count).to_dict() for c in children]
        if not valid_group_shape(nested["relation"], decoded):
            return _unknown(raw)
        return IntentTrigger(
            type="group",
            data={
                "relation": nested["relation"],
                "conditions": decoded,
                "_raw": deepcopy(raw),
            },
        )
    if kind in ("DEVICE", "CHECK_DEVICE"):
        typ = "device" if kind == "DEVICE" else "check_device"
        payload = raw.get(_DEVICE_KEYS[typ])
        if not isinstance(payload, dict) or not isinstance(payload.get("condition"), dict):
            return _unknown(raw)
        condition = payload["condition"]
        data = {
            "device_id": payload.get("device_id"),
            "attribute": deepcopy(condition.get("state")),
            "operator": condition.get("condition", "EQUAL"),
            "_raw": deepcopy(raw),
        }
        if not _valid_device(data):
            return _unknown(raw)
        if typ == "device":
            data.update(
                parent_id=payload.get("parent_id", ""),
                categories_slugs=deepcopy(payload.get("categories_slugs") or []),
                delay_seconds=parse_delay_seconds(condition.get("delay")),
            )
        return IntentTrigger(type=typ, data=data)
    if kind == "CHECK_SCENARIO":
        payload = raw.get("check_scenario_conditions_data")
        if (
            isinstance(payload, dict)
            and _text(payload.get("scenario_id"))
            and _text(payload.get("status"))
        ):
            return IntentTrigger(
                type="check_scenario",
                data={
                    "scenario_id": payload["scenario_id"],
                    "status": payload["status"],
                    "_raw": deepcopy(raw),
                },
            )
    return _unknown(raw)


def encode_condition(node: IntentTrigger) -> dict[str, Any]:
    """Encode a whole editable branch or fail before issuing any cloud request."""
    return _encode(node, 0, [0])


def _encode(node: IntentTrigger, depth: int, count: list[int]) -> dict[str, Any]:
    count[0] += 1
    if depth > MAX_CONDITION_DEPTH or count[0] > MAX_CONDITION_NODES:
        raise ValueError("Condition tree is too large")
    if node.unknown or node.type == "unknown":
        raw = node.data.get("raw")
        if not isinstance(raw, dict):
            raise ValueError("Unknown condition has no original data")
        return deepcopy(raw)
    data = node.data
    raw = deepcopy(data.get("_raw") or {})
    if node.type == "group":
        children = data.get("conditions")
        if (
            data.get("relation") not in ("AND", "OR")
            or not isinstance(children, list)
            or not children
            or not all(isinstance(c, dict) for c in children)
        ):
            raise ValueError("Choose AND/OR and add conditions to the group")
        if not valid_group_shape(data["relation"], children):
            raise ValueError(
                "AND requires one device event plus checks; OR requires events or groups"
            )
        nested = raw.get("nested_conditions_data") or {}
        nested.update(
            relation=data["relation"],
            conditions=[_encode(IntentTrigger.from_dict(c), depth + 1, count) for c in children],
        )
        raw.update(type="CONDITIONS", nested_conditions_data=nested)
    elif node.type in _DEVICE_KEYS:
        if not _valid_device(data):
            raise ValueError("Choose a device, attribute and comparison for every condition")
        key = _DEVICE_KEYS[node.type]
        payload = raw.get(key) or {}
        comparison = payload.get("condition") or {}
        state = deepcopy(data["attribute"])
        previous = comparison.get("state")
        if isinstance(previous, dict) and all(
            previous.get(k) == state.get(k) for k in ("key", "type")
        ):
            state = {**deepcopy(previous), **state}
        comparison.update(state=state, condition=data.get("operator", "EQUAL"))
        if node.type == "device":
            comparison["delay"] = f"{parse_delay_seconds(data.get('delay_seconds'))}s"
            if data.get("parent_id"):
                payload["parent_id"] = data["parent_id"]
            else:
                payload.pop("parent_id", None)
            payload["categories_slugs"] = deepcopy(data.get("categories_slugs") or [])
        payload.update(device_id=data["device_id"], condition=comparison)
        raw.update(type="DEVICE" if node.type == "device" else "CHECK_DEVICE", **{key: payload})
    elif node.type == "check_scenario":
        if not _text(data.get("scenario_id")) or not _text(data.get("status")):
            raise ValueError("Choose a scenario and its status")
        payload = raw.get("check_scenario_conditions_data") or {}
        payload.update(scenario_id=data["scenario_id"], status=data["status"])
        raw.update(type="CHECK_SCENARIO", check_scenario_conditions_data=payload)
    else:
        raise ValueError("Unsupported editable condition")
    return raw
