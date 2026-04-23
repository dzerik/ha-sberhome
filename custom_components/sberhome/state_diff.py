"""Per-device state-payload diff collector for DevTools.

Sber `reported_state` payloads re-send every attribute on every
update — both for WebSocket DEVICE_STATE push and full polling
refresh.  The raw message log therefore buries the actual change in
a wall of unchanged fields.  This collector remembers the previous
``{attr_key → value}`` mapping for each device and emits a compact
delta (``added`` / ``removed`` / ``changed``) so DevTools can render
one line per feature:

    light.kitchen (ws_push)
      ~ light_brightness: 50 → 75
      + light_colour: hsv(0, 100, 100)
      − light_mode

Design notes:
    * Pure Python, HA-independent.  Caller feeds already-serialized
      ``list[dict]`` (the JSON-ready shape from
      :meth:`AttributeValueDto.to_dict`) so the collector never has
      to know about dataclasses or ``AttributeValueType``.
    * Both ring buffer (chronological) and per-device baseline are
      kept in memory.  Same size envelope as the existing
      ``_ws_log`` / ``_ws_log_subscribers`` pattern in coordinator.py.
    * Empty deltas (payload identical to the previous one for that
      device) are dropped — nothing is recorded and no subscriber
      fires.  Keeps the log honest: every row represents real change.
"""

from __future__ import annotations

import copy
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class StateDiff:
    """Delta between two consecutive ``reported_state`` snapshots for one device."""

    ts: float
    device_id: str
    source: str
    """Origin of the snapshot: ``ws_push``, ``polling``, or ``inject``."""
    topic: str = ""
    """Sber topic when applicable (e.g. ``DEVICE_STATE``); empty for polling."""
    added: dict[str, Any] = field(default_factory=dict)
    """attr_key → full value dict (``{"type": ..., "*_value": ...}``)."""
    removed: dict[str, Any] = field(default_factory=dict)
    changed: dict[str, dict[str, Any]] = field(default_factory=dict)
    """changed[attr_key] = {"before": {...}, "after": {...}}."""
    is_initial: bool = False
    """True when this is the first snapshot ever seen for the device."""

    @property
    def is_empty(self) -> bool:
        """True when no attribute changed compared to the previous snapshot."""
        return not self.added and not self.removed and not self.changed

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


def _normalize_value(item: dict[str, Any]) -> dict[str, Any]:
    """Strip the ``key`` field and return a copy of the value payload.

    The incoming dict already carries ``key`` at the top level; we keep
    it only as the dict-key, not duplicated inside the value body.
    Also drops ``last_sync`` — it's a wall-clock timestamp that
    changes every publish and would make every comparison flag "changed".
    """
    out = {k: v for k, v in item.items() if k not in ("key", "last_sync")}
    return out


class DiffCollector:
    """In-memory ring buffer of recent state diffs with live subscribers."""

    def __init__(self, maxlen: int = 200, *, include_initial: bool = False) -> None:
        """Initialize a collector.

        Args:
            maxlen: Ring-buffer size for stored diffs.
            include_initial: Whether the very first snapshot for a
                device should produce a diff (everything under
                ``added``).  Off by default — startup otherwise
                floods the UI with the initial polling tree.
        """
        self._diffs: deque[StateDiff] = deque(maxlen=maxlen)
        self._last_by_device: dict[str, dict[str, Any]] = {}
        self._subscribers: set[Callable[[StateDiff], None]] = set()
        self._include_initial = include_initial

    # ------------------------------------------------------------------
    # Properties / config
    # ------------------------------------------------------------------

    @property
    def maxlen(self) -> int | None:
        """Return ring-buffer capacity."""
        return self._diffs.maxlen

    def resize(self, new_maxlen: int) -> None:
        """Resize the ring buffer, keeping the newest entries."""
        if new_maxlen == self._diffs.maxlen:
            return
        old = list(self._diffs)
        self._diffs = deque(old[-new_maxlen:], maxlen=new_maxlen)

    # ------------------------------------------------------------------
    # Snapshot / clear
    # ------------------------------------------------------------------

    def snapshot(self) -> list[dict[str, Any]]:
        """Return all stored diffs as JSON-serializable dicts, oldest first."""
        return [d.as_dict() for d in self._diffs]

    def clear(self) -> None:
        """Drop all stored diffs and the per-device baseline."""
        self._diffs.clear()
        self._last_by_device.clear()

    def reset_device(self, device_id: str) -> None:
        """Forget the baseline for one device (e.g. on removal)."""
        self._last_by_device.pop(device_id, None)

    def get_last_state(self, device_id: str) -> dict[str, Any] | None:
        """Return a deep copy of the baseline for a device, if any."""
        snap = self._last_by_device.get(device_id)
        return copy.deepcopy(snap) if snap is not None else None

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------

    def subscribe(self, callback_fn: Callable[[StateDiff], None]) -> Callable[[], None]:
        """Subscribe to non-empty diffs as they are recorded.

        Returns:
            Unsubscribe callable.
        """
        self._subscribers.add(callback_fn)

        def unsub() -> None:
            self._subscribers.discard(callback_fn)

        return unsub

    def _notify(self, diff: StateDiff) -> None:
        for cb in list(self._subscribers):
            try:
                cb(diff)
            except (RuntimeError, ValueError, TypeError, AttributeError):
                _LOGGER.exception("DiffCollector subscriber raised")

    # ------------------------------------------------------------------
    # Core: update(device_id, reported_state)
    # ------------------------------------------------------------------

    def update(
        self,
        device_id: str,
        reported_state: Iterable[dict[str, Any]],
        *,
        source: str = "ws_push",
        topic: str = "",
    ) -> StateDiff | None:
        """Compute the diff vs the previous snapshot and store it.

        Args:
            device_id: Sber device identifier.
            reported_state: The ``reported_state`` list from the
                payload — each item is ``{"key": str, "type": ...,
                "<typed>_value": ...}``.  Items without a ``key`` are
                ignored.
            source: Where the snapshot came from (``ws_push``,
                ``polling``, ``inject``).  Carried into the record so
                DevTools can colour/filter by origin.
            topic: Sber API topic when known (e.g. ``DEVICE_STATE``).
                Empty string when polling (no topic).

        Returns:
            The :class:`StateDiff` record (also appended to the ring
            buffer), or ``None`` when the payload is empty or nothing
            changed.
        """
        new_map: dict[str, Any] = {}
        for item in reported_state:
            key = item.get("key")
            if not key:
                continue
            new_map[key] = _normalize_value(item)

        prev = self._last_by_device.get(device_id)
        is_initial = prev is None
        self._last_by_device[device_id] = copy.deepcopy(new_map)

        if is_initial:
            if not self._include_initial or not new_map:
                return None
            diff = StateDiff(
                ts=time.time(),
                device_id=device_id,
                source=source,
                topic=topic,
                added=copy.deepcopy(new_map),
                is_initial=True,
            )
        else:
            added = {k: v for k, v in new_map.items() if k not in prev}
            removed = {k: v for k, v in prev.items() if k not in new_map}
            changed = {
                k: {"before": prev[k], "after": new_map[k]}
                for k in new_map
                if k in prev and prev[k] != new_map[k]
            }
            if not added and not removed and not changed:
                return None
            diff = StateDiff(
                ts=time.time(),
                device_id=device_id,
                source=source,
                topic=topic,
                added=copy.deepcopy(added),
                removed=copy.deepcopy(removed),
                changed=copy.deepcopy(changed),
            )

        self._diffs.append(diff)
        self._notify(diff)
        return diff
