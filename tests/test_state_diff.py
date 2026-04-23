"""Unit tests for :class:`DiffCollector`.

A broken diff collector silently loses real state changes or manufactures
phantom "changed" rows — both break the DevTools "what actually changed"
view without any other symptom.  These tests pin each algorithm branch
and the ring-buffer contract.
"""

from __future__ import annotations

import json

from custom_components.sberhome.state_diff import DiffCollector, StateDiff


def _attr(key: str, type_: str, **body) -> dict:
    """Build an already-serialized reported_state item."""
    return {"key": key, "type": type_, **body}


class TestInitialSnapshot:
    """First snapshot per device must establish a baseline."""

    def test_initial_default_drops_record(self) -> None:
        # The startup flood (initial polling tree for every device) must not
        # spam the DevTools log — baseline captured silently.
        dc = DiffCollector()
        assert dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)]) is None
        assert dc.get_last_state("dev-1") == {"on_off": {"type": "BOOL", "bool_value": True}}

    def test_initial_opt_in_emits_added_record(self) -> None:
        dc = DiffCollector(include_initial=True)
        res = dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        assert res is not None
        assert res.is_initial is True
        assert "on_off" in res.added

    def test_empty_initial_payload_returns_none(self) -> None:
        dc = DiffCollector(include_initial=True)
        assert dc.update("dev-1", []) is None


class TestDeltaMath:
    """Add / remove / change classification."""

    def _prime(self, dc: DiffCollector) -> None:
        dc.update(
            "dev-1",
            [
                _attr("on_off", "BOOL", bool_value=True),
                _attr("light_brightness", "INTEGER", integer_value=50),
            ],
        )

    def test_changed_has_before_and_after(self) -> None:
        dc = DiffCollector()
        self._prime(dc)
        res = dc.update(
            "dev-1",
            [
                _attr("on_off", "BOOL", bool_value=True),
                _attr("light_brightness", "INTEGER", integer_value=75),
            ],
        )
        assert res is not None
        # Both halves must be present — missing "before" makes the UI useless.
        assert res.changed == {
            "light_brightness": {
                "before": {"type": "INTEGER", "integer_value": 50},
                "after": {"type": "INTEGER", "integer_value": 75},
            }
        }
        assert res.added == {}
        assert res.removed == {}

    def test_added_key_lands_in_added(self) -> None:
        dc = DiffCollector()
        self._prime(dc)
        res = dc.update(
            "dev-1",
            [
                _attr("on_off", "BOOL", bool_value=True),
                _attr("light_brightness", "INTEGER", integer_value=50),
                _attr("light_colour", "COLOR", color_value={"h": 0, "s": 100, "v": 100}),
            ],
        )
        assert res is not None
        assert "light_colour" in res.added
        assert res.changed == {}

    def test_removed_key_lands_in_removed_with_prior_value(self) -> None:
        dc = DiffCollector()
        self._prime(dc)
        res = dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        assert res is not None
        # Keeping the prior value on removed helps the UI show what
        # disappeared; otherwise the removal card would be blank.
        assert res.removed == {"light_brightness": {"type": "INTEGER", "integer_value": 50}}

    def test_identical_payload_returns_none(self) -> None:
        dc = DiffCollector()
        self._prime(dc)
        assert (
            dc.update(
                "dev-1",
                [
                    _attr("on_off", "BOOL", bool_value=True),
                    _attr("light_brightness", "INTEGER", integer_value=50),
                ],
            )
            is None
        )

    def test_last_sync_is_ignored(self) -> None:
        # `last_sync` is a wall-clock stamp that changes every publish —
        # if we compared it, every snapshot would fake a "changed" row.
        dc = DiffCollector()
        dc.update(
            "dev-1",
            [_attr("on_off", "BOOL", bool_value=True, last_sync="2026-01-01T00:00:00Z")],
        )
        res = dc.update(
            "dev-1",
            [_attr("on_off", "BOOL", bool_value=True, last_sync="2026-04-22T10:00:00Z")],
        )
        assert res is None

    def test_entries_without_key_are_ignored(self) -> None:
        # Malformed item must not poison the baseline.
        dc = DiffCollector()
        self._prime(dc)
        res = dc.update(
            "dev-1",
            [
                _attr("on_off", "BOOL", bool_value=True),
                {"type": "INTEGER", "integer_value": 99},  # no "key"
                _attr("light_brightness", "INTEGER", integer_value=50),
            ],
        )
        assert res is None


class TestSourceAndTopic:
    """The origin of a snapshot is carried into the record."""

    def test_source_ws_push_is_default(self) -> None:
        dc = DiffCollector()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        res = dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])
        assert res is not None
        assert res.source == "ws_push"

    def test_source_polling_preserved(self) -> None:
        dc = DiffCollector()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)], source="polling")
        res = dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)], source="polling")
        assert res is not None
        assert res.source == "polling"

    def test_topic_propagates_into_record(self) -> None:
        # The UI tints "DEVICE_STATE" vs empty (polling) differently —
        # dropping this field would lose the visual distinction.
        dc = DiffCollector()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        res = dc.update(
            "dev-1",
            [_attr("on_off", "BOOL", bool_value=False)],
            topic="DEVICE_STATE",
        )
        assert res is not None
        assert res.topic == "DEVICE_STATE"


class TestBaselineLifecycle:
    def test_reset_device_makes_next_update_initial(self) -> None:
        dc = DiffCollector(include_initial=True)
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        dc.reset_device("dev-1")
        res = dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        assert res is not None and res.is_initial is True

    def test_devices_have_independent_baselines(self) -> None:
        # Cross-pollination between devices would be a catastrophic bug.
        dc = DiffCollector()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        dc.update("dev-2", [_attr("on_off", "BOOL", bool_value=False)])
        res = dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])
        assert res is not None
        assert res.changed["on_off"]["before"]["bool_value"] is True

    def test_get_last_state_returns_deep_copy(self) -> None:
        dc = DiffCollector()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        snap = dc.get_last_state("dev-1")
        assert snap is not None
        snap["on_off"]["bool_value"] = False
        # Mutating the returned snapshot must not leak back.
        assert dc.get_last_state("dev-1")["on_off"]["bool_value"] is True


class TestSubscribers:
    def test_subscriber_receives_only_non_empty_diffs(self) -> None:
        dc = DiffCollector()
        received: list[StateDiff] = []
        dc.subscribe(received.append)
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])  # initial — silent
        assert received == []
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])  # real change
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])  # no change
        assert len(received) == 1

    def test_unsubscribe_stops_delivery(self) -> None:
        dc = DiffCollector()
        received: list[StateDiff] = []
        unsub = dc.subscribe(received.append)
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])
        unsub()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        assert len(received) == 1

    def test_bad_subscriber_does_not_break_collector(self) -> None:
        dc = DiffCollector()

        def bad(_d: StateDiff) -> None:
            raise RuntimeError("boom")

        dc.subscribe(bad)
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        # Must not raise — a buggy UI subscriber must not take HA down.
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])


class TestRingBuffer:
    def test_maxlen_trims_oldest(self) -> None:
        dc = DiffCollector(maxlen=3)
        for i in range(5):
            dc.update(f"dev-{i}", [_attr("on_off", "BOOL", bool_value=True)])
            dc.update(f"dev-{i}", [_attr("on_off", "BOOL", bool_value=False)])
        assert len(dc.snapshot()) == 3

    def test_resize_keeps_newest(self) -> None:
        dc = DiffCollector(maxlen=10)
        for i in range(4):
            dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=i % 2 == 0)])
        dc.resize(2)
        assert len(dc.snapshot()) == 2

    def test_clear_resets_everything(self) -> None:
        dc = DiffCollector()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])
        dc.clear()
        assert dc.snapshot() == []
        # Baseline must go with the clear — otherwise the next update
        # would fake a phantom "changed" against cleared history.
        assert dc.get_last_state("dev-1") is None


class TestSerialization:
    def test_as_dict_is_json_serializable(self) -> None:
        dc = DiffCollector()
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=True)])
        dc.update("dev-1", [_attr("on_off", "BOOL", bool_value=False)])
        data = json.dumps(dc.snapshot())
        # Field names read directly by the UI — renames silently break it.
        for field_name in ("device_id", "source", "changed", "before", "after"):
            assert f'"{field_name}"' in data
