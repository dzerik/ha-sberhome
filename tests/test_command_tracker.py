"""Unit tests for :class:`CommandTracker`.

Sber protocol has no correlation id — a wrong verdict here either
misses silent rejections (user loses trust in DevTools) or fakes them
for commands that actually worked (drives false-positive support
tickets).  Tests pin each lifecycle branch and the matching rules.
"""

from __future__ import annotations

import json
import time

from custom_components.sberhome.command_tracker import CommandRecord, CommandTracker


def _desired(*kv_pairs) -> list[dict]:
    """Build a desired_state list from ``(key, type, **body)`` tuples."""
    return [{"key": k, "type": t, **body} for k, t, body in kv_pairs]


class TestRecordSent:
    def test_record_produces_pending_command(self) -> None:
        ct = CommandTracker()
        cmd = ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        assert cmd is not None
        assert cmd.status == "pending"
        assert cmd.device_id == "dev-1"
        assert set(cmd.keys_sent) == {"on_off"}

    def test_empty_desired_state_returns_none(self) -> None:
        # Nothing to confirm — no record; otherwise sweep() would
        # silent-reject a command nobody sent.
        ct = CommandTracker()
        assert ct.record_sent("dev-1", []) is None

    def test_items_without_key_are_ignored(self) -> None:
        ct = CommandTracker()
        # Only the well-formed item survives.
        cmd = ct.record_sent(
            "dev-1",
            [
                {"type": "BOOL", "bool_value": True},  # no key
                {"key": "on_off", "type": "BOOL", "bool_value": True},
            ],
        )
        assert cmd is not None
        assert set(cmd.keys_sent) == {"on_off"}


class TestObserveReportedState:
    def test_matching_reported_confirms_and_closes(self) -> None:
        ct = CommandTracker()
        cmd = ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        affected = ct.observe_reported_state(
            "dev-1",
            [{"key": "on_off", "type": "BOOL", "bool_value": True}],
        )
        assert affected == [cmd.command_id]
        # Closed and confirmed — the whole point of the tracker.
        assert ct.get(cmd.command_id)["status"] == "confirmed"

    def test_different_value_does_not_confirm(self) -> None:
        # Device accepted the HTTP but reported a different value —
        # that's the classic "ignored" pattern, NOT confirmation.
        ct = CommandTracker()
        cmd = ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        ct.observe_reported_state(
            "dev-1",
            [{"key": "on_off", "type": "BOOL", "bool_value": False}],
        )
        assert ct.get(cmd.command_id)["status"] == "pending"

    def test_partial_confirmation_keeps_command_pending(self) -> None:
        ct = CommandTracker()
        cmd = ct.record_sent(
            "dev-1",
            _desired(
                ("on_off", "BOOL", {"bool_value": True}),
                ("light_brightness", "INTEGER", {"integer_value": 75}),
            ),
        )
        # Only one of the two keys appears in reported_state.
        affected = ct.observe_reported_state(
            "dev-1",
            [{"key": "on_off", "type": "BOOL", "bool_value": True}],
        )
        assert affected == [cmd.command_id]
        view = ct.get(cmd.command_id)
        assert view["status"] == "pending"
        assert "on_off" in view["keys_confirmed"]
        assert "light_brightness" not in view["keys_confirmed"]

    def test_last_sync_does_not_block_match(self) -> None:
        # Sber server adds a wall-clock `last_sync` to every value —
        # if the tracker compared it, no command would ever confirm.
        ct = CommandTracker()
        cmd = ct.record_sent(
            "dev-1",
            _desired(("on_off", "BOOL", {"bool_value": True, "last_sync": "T0"})),
        )
        ct.observe_reported_state(
            "dev-1",
            [
                {
                    "key": "on_off",
                    "type": "BOOL",
                    "bool_value": True,
                    "last_sync": "T1",
                },
            ],
        )
        assert ct.get(cmd.command_id)["status"] == "confirmed"

    def test_observation_for_other_device_is_ignored(self) -> None:
        # Cross-device leakage would confirm a command against a
        # totally unrelated device's reported_state.
        ct = CommandTracker()
        cmd = ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        ct.observe_reported_state(
            "dev-2",
            [{"key": "on_off", "type": "BOOL", "bool_value": True}],
        )
        assert ct.get(cmd.command_id)["status"] == "pending"


class TestSweep:
    def test_timeout_with_no_confirmation_is_silent_rejection(self) -> None:
        ct = CommandTracker(command_timeout=0.01)
        cmd = ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        time.sleep(0.02)
        closed = ct.sweep()
        assert closed == [cmd.command_id]
        # Zero confirmations + timeout = explicit silent rejection
        # (Sber accepted HTTP but device didn't apply).
        assert ct.get(cmd.command_id)["status"] == "silent_rejection"

    def test_timeout_with_partial_confirmation_is_partial(self) -> None:
        ct = CommandTracker(command_timeout=0.01)
        cmd = ct.record_sent(
            "dev-1",
            _desired(
                ("on_off", "BOOL", {"bool_value": True}),
                ("light_brightness", "INTEGER", {"integer_value": 75}),
            ),
        )
        ct.observe_reported_state(
            "dev-1",
            [{"key": "on_off", "type": "BOOL", "bool_value": True}],
        )
        time.sleep(0.02)
        ct.sweep()
        assert ct.get(cmd.command_id)["status"] == "partial"

    def test_fresh_command_not_swept(self) -> None:
        ct = CommandTracker(command_timeout=10.0)
        cmd = ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        assert ct.sweep() == []
        assert ct.get(cmd.command_id)["status"] == "pending"


class TestSubscribers:
    def test_subscriber_sees_sent_and_closed(self) -> None:
        ct = CommandTracker()
        events: list[tuple[str, str]] = []
        ct.subscribe(lambda kind, c: events.append((kind, c.command_id)))
        cmd = ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        ct.observe_reported_state(
            "dev-1",
            [{"key": "on_off", "type": "BOOL", "bool_value": True}],
        )
        assert events == [("command_sent", cmd.command_id), ("command_closed", cmd.command_id)]

    def test_subscriber_exception_does_not_break_tracker(self) -> None:
        ct = CommandTracker()

        def bad(_kind, _cmd):
            raise RuntimeError("boom")

        ct.subscribe(bad)
        # Must not raise — a buggy UI subscriber must not take HA down.
        ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))


class TestRingBuffer:
    def test_maxlen_trims_oldest_closed(self) -> None:
        ct = CommandTracker(maxlen=3, command_timeout=0.01)
        for i in range(5):
            ct.record_sent(f"dev-{i}", _desired(("on_off", "BOOL", {"bool_value": True})))
        time.sleep(0.02)
        ct.sweep()
        assert len(ct.snapshot(include_active=False)) == 3


class TestSerialization:
    def test_snapshot_is_json_serializable(self) -> None:
        ct = CommandTracker()
        ct.record_sent("dev-1", _desired(("on_off", "BOOL", {"bool_value": True})))
        data = json.dumps(ct.snapshot())
        # Field names read directly by the UI — renames break it.
        for field_name in (
            "command_id",
            "device_id",
            "status",
            "keys_sent",
            "keys_confirmed",
        ):
            assert f'"{field_name}"' in data

    def test_record_as_dict_has_expected_fields(self) -> None:
        r = CommandRecord(
            command_id="x",
            device_id="dev-1",
            sent_at=0.0,
            keys_sent={"on_off": {"type": "BOOL", "bool_value": True}},
        )
        assert set(r.as_dict().keys()) == {
            "command_id",
            "device_id",
            "sent_at",
            "keys_sent",
            "keys_confirmed",
            "status",
            "closed_at",
        }
