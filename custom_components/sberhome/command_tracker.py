"""Command-confirmation tracker for DevTools.

Unlike MQTT-SberGate's correlation-timeline feature (which leans on
HA's built-in ``Context.id``), the Sber REST/WS protocol has **no
correlation id** on either side.  A ``PUT /devices/{id}/state``
returns an HTTP 200 regardless of whether the device actually applied
the desired value — the only way to know the command really worked is
to watch the next ``reported_state`` for the same device and see our
keys land at the requested values (or not).

This tracker records every outbound command and waits for either:
    * **confirmed** — every requested key showed up in a subsequent
      ``reported_state`` with the expected value;
    * **partial** — at least one key was confirmed, but one or more
      are still missing after the timeout window;
    * **silent_rejection** — the timeout expired and no key was
      confirmed (Sber accepted the HTTP request but didn't apply
      anything).

The result is how the DevTools panel spots silent rejections without
the correlation id the protocol is missing.

Design:
    * Pure Python, HA-independent.  Callers feed it already-serialized
      ``list[dict]`` (the JSON-ready shape) so the tracker doesn't
      have to know about ``AttributeValueDto`` / ``AttributeValueType``.
    * Time-based: entries auto-close after ``command_timeout`` seconds
      on the next :meth:`sweep` call, which the coordinator runs from
      the existing polling tick.  No background tasks owned here.
    * Both active and closed entries are JSON-serializable — the WS
      API just returns ``snapshot()``.
"""

from __future__ import annotations

import copy
import logging
import time
import uuid
from collections import deque
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

_LOGGER = logging.getLogger(__name__)

CommandStatus = Literal["pending", "confirmed", "partial", "silent_rejection"]
SubscriberEvent = Literal["command_sent", "command_updated", "command_closed"]


@dataclass
class CommandRecord:
    """One tracked outbound command."""

    command_id: str
    device_id: str
    sent_at: float
    keys_sent: dict[str, Any]  # attr_key → sent value dict
    keys_confirmed: dict[str, Any] = field(default_factory=dict)
    """attr_key → confirmed value dict (what landed in reported_state)."""
    status: CommandStatus = "pending"
    closed_at: float | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)

    def pending_keys(self) -> set[str]:
        """Keys still waiting to show up in reported_state."""
        return set(self.keys_sent) - set(self.keys_confirmed)


def _value_equals(sent: Any, observed: Any) -> bool:
    """Compare two AttributeValueDto-shaped dicts, ignoring ``last_sync``.

    The tracker treats two values as equal when all *typed* fields
    match.  ``last_sync`` is the server-side ISO timestamp that
    changes on every publish and would otherwise make every
    confirmation look like a mismatch.
    """
    if not isinstance(sent, dict) or not isinstance(observed, dict):
        return sent == observed
    s = {k: v for k, v in sent.items() if k not in ("key", "last_sync")}
    o = {k: v for k, v in observed.items() if k not in ("key", "last_sync")}
    return s == o


class CommandTracker:
    """In-memory store of recent outbound commands + live subscribers."""

    def __init__(
        self,
        *,
        maxlen: int = 200,
        command_timeout: float = 10.0,
    ) -> None:
        """Initialize a tracker.

        Args:
            maxlen: Ring-buffer size for closed commands.
            command_timeout: Seconds after which a pending command is
                auto-closed on :meth:`sweep` (with
                ``silent_rejection`` or ``partial`` status depending
                on how many keys were confirmed).
        """
        self._active: dict[str, CommandRecord] = {}
        self._closed: deque[CommandRecord] = deque(maxlen=maxlen)
        self._command_timeout = command_timeout
        self._subscribers: set[Callable[[SubscriberEvent, CommandRecord], None]] = set()

    # ------------------------------------------------------------------
    # Properties / config
    # ------------------------------------------------------------------

    @property
    def maxlen(self) -> int | None:
        """Return the closed-command ring-buffer capacity."""
        return self._closed.maxlen

    @property
    def command_timeout(self) -> float:
        """Return the configured timeout in seconds."""
        return self._command_timeout

    def set_command_timeout(self, seconds: float) -> None:
        """Update the timeout."""
        self._command_timeout = seconds

    def resize(self, new_maxlen: int) -> None:
        """Resize the ring buffer, keeping the newest entries."""
        if new_maxlen == self._closed.maxlen:
            return
        old = list(self._closed)
        self._closed = deque(old[-new_maxlen:], maxlen=new_maxlen)

    # ------------------------------------------------------------------
    # Snapshot / clear
    # ------------------------------------------------------------------

    def snapshot(self, *, include_active: bool = True) -> list[dict[str, Any]]:
        """Return closed + active commands, oldest first."""
        out = [c.as_dict() for c in self._closed]
        if include_active:
            out.extend(c.as_dict() for c in self._active.values())
        return out

    def clear(self) -> None:
        """Drop all active and closed commands."""
        self._active.clear()
        self._closed.clear()

    def get(self, command_id: str) -> dict[str, Any] | None:
        """Return one command by id, or ``None``."""
        cmd = self._active.get(command_id)
        if cmd is not None:
            return cmd.as_dict()
        for c in self._closed:
            if c.command_id == command_id:
                return c.as_dict()
        return None

    # ------------------------------------------------------------------
    # Subscribers
    # ------------------------------------------------------------------

    def subscribe(
        self, callback_fn: Callable[[SubscriberEvent, CommandRecord], None]
    ) -> Callable[[], None]:
        """Subscribe to command lifecycle events."""
        self._subscribers.add(callback_fn)

        def unsub() -> None:
            self._subscribers.discard(callback_fn)

        return unsub

    def _notify(self, kind: SubscriberEvent, cmd: CommandRecord) -> None:
        for cb in list(self._subscribers):
            try:
                cb(kind, cmd)
            except (RuntimeError, ValueError, TypeError, AttributeError):
                _LOGGER.exception("CommandTracker subscriber raised")

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def record_sent(
        self,
        device_id: str,
        desired_state: Iterable[dict[str, Any]],
    ) -> CommandRecord | None:
        """Register an outbound ``PUT /devices/{device_id}/state``.

        Args:
            device_id: Target Sber device identifier.
            desired_state: The ``state`` array sent in the request —
                list of ``{"key": str, "type": ..., "*_value": ...}``.
                Items without ``key`` are ignored; an empty iterable
                does not produce a record (no confirmation is
                possible anyway).

        Returns:
            The new :class:`CommandRecord`, or ``None`` when
            ``desired_state`` has no ``key``-bearing items.
        """
        keys_sent: dict[str, Any] = {}
        for item in desired_state:
            key = item.get("key")
            if not key:
                continue
            body = {k: v for k, v in item.items() if k not in ("key", "last_sync")}
            keys_sent[key] = body
        if not keys_sent:
            return None
        cmd = CommandRecord(
            command_id=uuid.uuid4().hex[:12],
            device_id=device_id,
            sent_at=time.time(),
            keys_sent=copy.deepcopy(keys_sent),
        )
        self._active[cmd.command_id] = cmd
        self._notify("command_sent", cmd)
        return cmd

    def observe_reported_state(
        self,
        device_id: str,
        reported_state: Iterable[dict[str, Any]],
    ) -> list[str]:
        """Check any pending commands for this device against a new snapshot.

        Walks the active pool, finds commands that match ``device_id``,
        and confirms each key for which the observed value equals what
        was sent.  When every key of a command is confirmed, the
        command closes with ``status="confirmed"``.

        Returns:
            List of command_ids whose status changed in this call.
        """
        observed_map: dict[str, dict[str, Any]] = {}
        for item in reported_state:
            key = item.get("key")
            if not key:
                continue
            observed_map[key] = {k: v for k, v in item.items() if k not in ("key", "last_sync")}

        if not observed_map:
            return []

        affected: list[str] = []
        for cmd in list(self._active.values()):
            if cmd.device_id != device_id:
                continue
            newly_confirmed = False
            for key, sent_value in cmd.keys_sent.items():
                if key in cmd.keys_confirmed:
                    continue
                if key not in observed_map:
                    continue
                if _value_equals(sent_value, observed_map[key]):
                    cmd.keys_confirmed[key] = copy.deepcopy(observed_map[key])
                    newly_confirmed = True
            if not newly_confirmed:
                continue
            if cmd.keys_confirmed.keys() == cmd.keys_sent.keys():
                cmd.status = "confirmed"
                cmd.closed_at = time.time()
                self._active.pop(cmd.command_id, None)
                self._closed.append(cmd)
                self._notify("command_closed", cmd)
            else:
                self._notify("command_updated", cmd)
            affected.append(cmd.command_id)
        return affected

    def sweep(self) -> list[str]:
        """Close commands older than the timeout.

        Returns command_ids that were closed.
        """
        now = time.time()
        closed_ids: list[str] = []
        for cmd in list(self._active.values()):
            if now - cmd.sent_at < self._command_timeout:
                continue
            if cmd.keys_confirmed:
                cmd.status = "partial"
            else:
                cmd.status = "silent_rejection"
            cmd.closed_at = now
            self._active.pop(cmd.command_id, None)
            self._closed.append(cmd)
            self._notify("command_closed", cmd)
            closed_ids.append(cmd.command_id)
        return closed_ids
