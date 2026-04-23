"""Unit tests for the inbound schema validator.

The validator is an early-warning system for Sber API drift.  False
negatives (real problem not flagged) mean we only notice drift when
a platform breaks; false positives spam the log and train users to
ignore it.  Tests pin each rule and the collector views.
"""

from __future__ import annotations

import json

from custom_components.sberhome.schema_validator import (
    ValidationCollector,
    ValidationIssue,
    validate_reported_state,
)


def _v(key: str, type_: str, **body) -> dict:
    return {"key": key, "type": type_, **body}


class TestUnknownValueType:
    def test_new_type_surfaces_warning(self) -> None:
        # Sber shipped a new AttributeValueType we haven't modelled —
        # typed accessors would silently return None until we update.
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("on_off", "FUTURE_TYPE", future_value="xxx")],
        )
        types = {i.type for i in issues}
        assert "unknown_value_type" in types

    def test_unknown_type_skips_value_consistency_checks(self) -> None:
        # Without knowing the type we can't tell what the correct
        # value field would be — so we must NOT emit missing_typed_value
        # alongside unknown_value_type (spam).
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("on_off", "FUTURE_TYPE")],
        )
        types = {i.type for i in issues}
        assert "missing_typed_value" not in types
        assert "wrong_typed_value" not in types


class TestMissingTypedValue:
    def test_declared_bool_without_bool_value_is_warning(self) -> None:
        # Payload literally omits bool_value — genuinely malformed.
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[{"key": "on_off", "type": "BOOL"}],
        )
        assert any(i.type == "missing_typed_value" for i in issues)

    def test_correct_pair_no_issue(self) -> None:
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("on_off", "BOOL", bool_value=True)],
        )
        assert issues == []

    def test_sber_wire_format_with_default_foreign_fields_is_clean(self) -> None:
        # The serialized format Sber actually sends: every primitive *_value
        # field present with its zero default alongside the real one.
        # Regression for the spam the user saw on every single attribute.
        sber_payload = {
            "key": "online",
            "type": "BOOL",
            "string_value": "",
            "integer_value": "0",  # note: string type on the API
            "float_value": 0,
            "bool_value": True,
            "enum_value": "",
            "last_sync": "2026-04-22T13:02:20.658504929Z",
        }
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[sber_payload],
        )
        assert issues == []

    def test_attribute_value_dto_to_dict_roundtrips_cleanly(self) -> None:
        # Integration-level: validator must not flag a clean
        # AttributeValueDto → to_dict roundtrip for any value type.
        from custom_components.sberhome.aiosber.dto import (
            AttributeValueDto,
        )

        dtos = [
            AttributeValueDto.of_bool("on_off", True),
            AttributeValueDto.of_int("battery_percentage", 87),
            AttributeValueDto.of_float("temperature", 21.3),
            AttributeValueDto.of_string("source", "hdmi_1"),
            AttributeValueDto.of_enum("hvac_work_mode", "cooling"),
        ]
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[d.to_dict() for d in dtos],
        )
        assert issues == []

    def test_bool_with_only_integer_value_present_still_flags_missing(self) -> None:
        # The expected bool_value is physically absent from the dict.
        # wrong_typed_value has been dropped (serialized format noise makes it
        # unreliable) — but missing_typed_value is still the truth here.
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("on_off", "BOOL", integer_value=1)],
        )
        types = {i.type for i in issues}
        assert "missing_typed_value" in types
        assert "wrong_typed_value" not in types


class TestUnknownAttrKey:
    def test_unseen_key_surfaces_info_finding(self) -> None:
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("quantum_entanglement_mode", "BOOL", bool_value=True)],
        )
        assert any(i.type == "unknown_attr_key" and i.severity == "info" for i in issues)

    def test_known_static_key_accepted(self) -> None:
        # on_off is a well-known AttrKey constant.
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("on_off", "BOOL", bool_value=True)],
        )
        assert not any(i.type == "unknown_attr_key" for i in issues)

    def test_dynamic_button_event_key_accepted(self) -> None:
        # button_1_event .. button_10_event etc. are generated at
        # runtime — patterns must recognise them, otherwise every
        # button press fires a false-positive warning.
        for key in ("button_3_event", "button_left_event", "button_bottom_right_event"):
            issues = validate_reported_state(
                device_id="dev-1",
                reported_state=[_v(key, "ENUM", enum_value="click")],
            )
            assert not any(i.type == "unknown_attr_key" for i in issues), (
                f"pattern missed for {key}"
            )


class TestCollector:
    def test_record_replaces_per_device_view(self) -> None:
        # Per-device snapshot must flip back to empty when the next
        # snapshot is clean — otherwise fixes never surface in the UI.
        coll = ValidationCollector()
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("xyz", "BOOL", bool_value=True)],
        )
        coll.record("dev-1", issues)
        coll.record("dev-1", [])
        assert coll.snapshot()["by_device"]["dev-1"] == []

    def test_recent_keeps_historical_issues(self) -> None:
        # Even after a clean snapshot, the chronological feed must
        # keep the historical issue so users can scroll back.
        coll = ValidationCollector()
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("xyz", "BOOL", bool_value=True)],
        )
        coll.record("dev-1", issues)
        coll.record("dev-1", [])
        assert len(coll.snapshot()["recent"]) == len(issues)

    def test_subscribers_called_only_for_non_empty_batches(self) -> None:
        coll = ValidationCollector()
        seen: list[list[ValidationIssue]] = []
        coll.subscribe(seen.append)
        coll.record("dev-1", [])
        assert seen == []
        issues = validate_reported_state(
            device_id="dev-1",
            reported_state=[_v("xyz", "BOOL", bool_value=True)],
        )
        coll.record("dev-1", issues)
        assert len(seen) == 1

    def test_subscriber_exception_does_not_break_collector(self) -> None:
        coll = ValidationCollector()

        def bad(_i):
            raise RuntimeError("boom")

        coll.subscribe(bad)
        # Must not raise — a buggy UI subscriber must not take HA down.
        coll.record(
            "dev-1",
            validate_reported_state(
                device_id="dev-1",
                reported_state=[_v("xyz", "BOOL", bool_value=True)],
            ),
        )

    def test_clear_drops_both_views(self) -> None:
        coll = ValidationCollector()
        coll.record(
            "dev-1",
            validate_reported_state(
                device_id="dev-1",
                reported_state=[_v("xyz", "BOOL", bool_value=True)],
            ),
        )
        coll.clear()
        assert coll.snapshot() == {"recent": [], "by_device": {}}

    def test_observe_reported_state_returns_issues(self) -> None:
        # Convenience entry point used by the coordinator hook.
        coll = ValidationCollector()
        res = coll.observe_reported_state("dev-1", [_v("xyz", "BOOL", bool_value=True)])
        assert res
        assert coll.snapshot()["by_device"]["dev-1"]


class TestSerialization:
    def test_snapshot_is_json_serializable(self) -> None:
        coll = ValidationCollector()
        coll.record(
            "dev-1",
            validate_reported_state(
                device_id="dev-1",
                reported_state=[_v("xyz", "BOOL", bool_value=True)],
            ),
        )
        data = json.dumps(coll.snapshot())
        for field_name in ("device_id", "severity", "type", "description"):
            assert f'"{field_name}"' in data
