"""Inbound REST/WS payload schema validator for DevTools.

Unlike MQTT-SberGate's validator — which had an authoritative
JSON spec of obligatory features per category — the Sber REST/WS
gateway API has no such reference.  Our source-of-truth for "what a
well-formed attribute looks like" is the integration's own DTO
surface: :class:`AttributeValueType` (8-variant enum) and the
:class:`AttrKey` namespace (hand-curated list of known keys).

What this validator catches:

* **unknown_value_type** — ``type`` field is not in
  :class:`AttributeValueType`.  Means Sber shipped a new type we
  haven't modelled yet — typed accessors will silently return
  ``None`` until we update the DTO.
* **missing_typed_value** — ``type=BOOL`` but no ``bool_value``
  key (or the equivalent mismatch for INTEGER / FLOAT / STRING /
  ENUM / COLOR / SCHEDULE / JSON).  Malformed API message.
* **unknown_attr_key** — ``key`` is not in the ``AttrKey`` namespace
  (and doesn't match any known dynamic pattern like
  ``button_N_event``).  Signals either a new feature Sber started
  emitting or a category we haven't mapped — DevTools can flag
  this so we notice drift early instead of when something breaks.

What this validator intentionally does **not** catch:

* **Presence of foreign ``*_value`` fields.**  Sber REST/WS
  payloads always include every primitive value field with its
  zero value (``""``, ``0``, ``0.0``, ``false``) regardless of
  ``type``.  A ``type=BOOL`` attribute arrives as
  ``{bool_value: true, integer_value: 0, float_value: 0.0,
  string_value: "", enum_value: ""}``.  There is no reliable way
  to tell "zero-default padding" from "real non-BOOL value"
  because ``0``, ``0.0``, ``""`` are perfectly valid semantic
  values.  Flagging it drowned the log in false positives on
  every single attribute, so we trust ``type`` and move on.

Design mirrors :mod:`custom_components.sberhome.state_diff` and
``command_tracker``:

* Pure Python, HA-independent.  Input is already-serialized
  ``list[dict]``.
* :class:`ValidationCollector` keeps both a chronological ring
  buffer (``recent``) and a per-device latest-snapshot
  (``by_device``) so the UI can answer both "what happened" and
  "which devices are currently broken".
"""

from __future__ import annotations

import logging
import re
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Any, Literal

from .aiosber.dto.attrs import AttrKey
from .aiosber.dto.enums import AttributeValueType

_LOGGER = logging.getLogger(__name__)

IssueType = Literal[
    "unknown_value_type",
    "missing_typed_value",
    "unknown_attr_key",
]
Severity = Literal["error", "warning", "info", "ok"]

_SEVERITY: dict[IssueType, Severity] = {
    "unknown_value_type": "warning",
    "missing_typed_value": "warning",
    "unknown_attr_key": "info",
}

# Map AttributeValueType.value → expected *_value field name on the API.
_TYPE_TO_VALUE_FIELD: dict[str, str] = {
    "STRING": "string_value",
    "INTEGER": "integer_value",
    "FLOAT": "float_value",
    "BOOL": "bool_value",
    "ENUM": "enum_value",
    "JSON": "json_value",
    "COLOR": "color_value",
    "SCHEDULE": "schedule_value",
}


def _known_attr_keys() -> frozenset[str]:
    """Collect every string-valued constant declared on :class:`AttrKey`."""
    out: set[str] = set()
    for name in vars(AttrKey):
        if name.startswith("_"):
            continue
        value = getattr(AttrKey, name)
        if isinstance(value, str):
            out.add(value)
    return frozenset(out)


_KNOWN_KEYS: frozenset[str] = _known_attr_keys()

# Dynamic keys that can't be listed as constants.  Documented in
# :func:`aiosber.dto.attrs.button_event_key` — one per physical button
# (up to 10) plus left/right/bottom/top variants.
_DYNAMIC_KEY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^button_(\d+|top|bottom|left|right|top_left|top_right|bottom_left|bottom_right)_event$"
    ),
)


def _is_known_key(key: str) -> bool:
    """Return True when ``key`` matches the static list or a dynamic pattern."""
    if key in _KNOWN_KEYS:
        return True
    return any(p.match(key) for p in _DYNAMIC_KEY_PATTERNS)


@dataclass(frozen=True)
class ValidationIssue:
    """One validation problem found in a reported_state snapshot."""

    ts: float
    device_id: str
    type: IssueType
    severity: Severity
    key: str | None
    description: str
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def validate_reported_state(
    *,
    device_id: str,
    reported_state: Iterable[dict[str, Any]],
) -> list[ValidationIssue]:
    """Classify every issue in one device's inbound snapshot."""
    now = time.time()
    issues: list[ValidationIssue] = []
    known_type_values = {t.value for t in AttributeValueType}

    for item in reported_state:
        key = item.get("key")
        type_value = item.get("type")

        if key is not None and not _is_known_key(key):
            issues.append(
                ValidationIssue(
                    ts=now,
                    device_id=device_id,
                    type="unknown_attr_key",
                    severity=_SEVERITY["unknown_attr_key"],
                    key=key,
                    description=(
                        f"Attribute key '{key}' is not in the integration's "
                        "known AttrKey list.  Probably a new feature from "
                        "Sber — may need a DTO/mapping update."
                    ),
                    details={},
                )
            )

        if type_value is not None and type_value not in known_type_values:
            issues.append(
                ValidationIssue(
                    ts=now,
                    device_id=device_id,
                    type="unknown_value_type",
                    severity=_SEVERITY["unknown_value_type"],
                    key=key,
                    description=(
                        f"Unknown AttributeValueType '{type_value}'.  This "
                        "is a breaking API change: typed "
                        "accessors won't know how to read it."
                    ),
                    details={"actual": type_value},
                )
            )
            # Skip further checks for this item — they're type-dependent.
            continue

        if type_value in _TYPE_TO_VALUE_FIELD:
            expected_field = _TYPE_TO_VALUE_FIELD[type_value]
            # Sber's REST/WS API always includes every primitive *_value
            # field — `bool_value`, `integer_value`, `float_value`,
            # `string_value`, `enum_value` — with zero defaults (``""``,
            # ``0``, ``0.0``, ``false``).  The *only* reliable
            # malformation signal is that the expected field is missing
            # from the dict outright.  Empty / zero values are common
            # legitimate readings (power=0W, brightness=0, humidity=0%)
            # so we cannot treat them as "missing".
            if expected_field not in item:
                issues.append(
                    ValidationIssue(
                        ts=now,
                        device_id=device_id,
                        type="missing_typed_value",
                        severity=_SEVERITY["missing_typed_value"],
                        key=key,
                        description=(
                            f"type='{type_value}' declares '{expected_field}' "
                            "but the field is absent from the payload."
                        ),
                        details={"expected_field": expected_field},
                    )
                )

    return issues


class ValidationCollector:
    """In-memory store of validation issues with live subscribe fan-out."""

    def __init__(self, maxlen: int = 500) -> None:
        """Initialize a collector with the given ring-buffer capacity."""
        self._recent: deque[ValidationIssue] = deque(maxlen=maxlen)
        self._by_device: dict[str, list[ValidationIssue]] = {}
        self._subscribers: set[Callable[[list[ValidationIssue]], None]] = set()

    @property
    def maxlen(self) -> int | None:
        """Return ring-buffer capacity."""
        return self._recent.maxlen

    def resize(self, new_maxlen: int) -> None:
        """Resize the ring buffer keeping the newest entries."""
        if new_maxlen == self._recent.maxlen:
            return
        old = list(self._recent)
        self._recent = deque(old[-new_maxlen:], maxlen=new_maxlen)

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of both views."""
        return {
            "recent": [i.as_dict() for i in self._recent],
            "by_device": {
                did: [i.as_dict() for i in issues] for did, issues in self._by_device.items()
            },
        }

    def clear(self) -> None:
        """Drop all stored issues."""
        self._recent.clear()
        self._by_device.clear()

    def record(self, device_id: str, issues: list[ValidationIssue]) -> None:
        """Persist the set of issues for ``device_id`` after a snapshot.

        A subsequent clean snapshot overwrites the per-device list, so the
        UI sees the device flip from red to clean as soon as the problem
        is fixed upstream.  The chronological ``recent`` buffer keeps
        history either way.
        """
        self._by_device[device_id] = list(issues)
        for i in issues:
            self._recent.append(i)
        if issues:
            self._notify(issues)

    def subscribe(self, callback_fn: Callable[[list[ValidationIssue]], None]) -> Callable[[], None]:
        """Subscribe to validation bursts (one call per snapshot with issues)."""
        self._subscribers.add(callback_fn)

        def unsub() -> None:
            self._subscribers.discard(callback_fn)

        return unsub

    def _notify(self, issues: list[ValidationIssue]) -> None:
        for cb in list(self._subscribers):
            try:
                cb(issues)
            except (RuntimeError, ValueError, TypeError, AttributeError):
                _LOGGER.exception("ValidationCollector subscriber raised")

    def observe_reported_state(
        self,
        device_id: str,
        reported_state: Iterable[dict[str, Any]],
    ) -> list[ValidationIssue]:
        """Validate a reported_state snapshot and record the issues."""
        issues = validate_reported_state(device_id=device_id, reported_state=reported_state)
        self.record(device_id, issues)
        return issues
