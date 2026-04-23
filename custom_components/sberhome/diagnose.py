"""Per-device "why isn't it working?" diagnostic advisor.

Gathers every signal the coordinator already exposes about one Sber
device — whether it's in the cloud tree, enabled by the user, mapped
to HA entities, online, fresh, and how the integration itself is doing
(WS connectivity, token freshness, recent error count) — then runs a
cheap rule-based check that turns the raw data into an actionable
verdict for the DevTools panel.

Design:
    * Pure function of ``coordinator`` state — no timers, no side
      effects.  Every rule returns a :class:`Finding` with
      ``severity`` so the UI can colour-code; the report verdict is
      the worst severity present (``broken`` > ``warning`` > ``ok``).
    * Rules are deliberately independent one-liners — adding a new
      heuristic is a single function, no orchestrator changes.
    * Some rules are per-device (``not_in_tree``, ``offline``) and
      some are integration-wide (``ws_disconnected``,
      ``token_expiring``).  Integration-wide rules get added to every
      report so users see global health next to the per-device story.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from .coordinator import SberHomeCoordinator

Severity = Literal["error", "warning", "info", "ok"]
Verdict = Literal["ok", "warning", "broken"]

# Freshness thresholds — sensors should show new reported_state at
# least every few minutes on a healthy install.  These are advisory,
# not hard cutoffs.
_STALE_WARNING_SECONDS = 30 * 60  # 30 minutes without any WS push or polling change
_TOKEN_WARN_LEEWAY_SECONDS = 24 * 3600  # 24h to companion/sberid expiry


@dataclass(frozen=True)
class Finding:
    """One observation produced by a diagnostic rule."""

    code: str
    severity: Severity
    title: str
    detail: str
    action: str = ""

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return asdict(self)


@dataclass
class DiagnosticReport:
    """Aggregated per-device diagnostic."""

    device_id: str
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "device_id": self.device_id,
            "verdict": self.verdict,
            "findings": [f.as_dict() for f in self.findings],
            "summary": self.summary,
        }


def _verdict_for(severities: list[Severity]) -> Verdict:
    """Reduce a list of severities into a single trace-level verdict."""
    if "error" in severities:
        return "broken"
    if "warning" in severities:
        return "warning"
    return "ok"


def _reported_map(dto: Any) -> dict[str, Any]:
    """Return ``{attr_key → AttributeValueDto}`` for a DeviceDto."""
    if dto is None:
        return {}
    return {a.key: a for a in dto.reported_state if a.key}


def _seconds_since(ts: float | None) -> float | None:
    """Seconds elapsed since ``ts`` (epoch).  ``None`` when no ts."""
    return None if ts is None else time.time() - ts


def _parse_last_sync(ts_str: str | None) -> float | None:
    """Parse ``last_sync`` ISO string into epoch seconds, best-effort."""
    if not ts_str or not isinstance(ts_str, str):
        return None
    from datetime import datetime

    try:
        # Typical Sber format: "2026-04-22T10:14:23.471Z".
        if ts_str.endswith("Z"):
            ts_str = ts_str[:-1] + "+00:00"
        return datetime.fromisoformat(ts_str).timestamp()
    except (ValueError, TypeError):
        return None


def _collect_summary(coord: SberHomeCoordinator, device_id: str) -> dict[str, Any]:
    """Gather raw state about the device for the UI to render as-is."""
    dto = coord.state_cache.get_device(device_id)
    enabled = coord.enabled_device_ids
    is_enabled = enabled is None or device_id in enabled
    ha_entities = coord.entities.get(device_id, [])
    reported = _reported_map(dto)

    online_attr = reported.get("online")
    online_value: bool | None = None
    if online_attr is not None:
        online_value = getattr(online_attr, "bool_value", None)

    # Pick the freshest last_sync across attributes as a freshness proxy.
    last_sync_ts: float | None = None
    for attr in reported.values():
        ts = _parse_last_sync(getattr(attr, "last_sync", None))
        if ts is not None and (last_sync_ts is None or ts > last_sync_ts):
            last_sync_ts = ts

    return {
        "in_tree": dto is not None,
        "enabled": is_enabled,
        "image_set_type": getattr(dto, "image_set_type", None) if dto else None,
        "name": getattr(dto, "display_name", None) if dto else None,
        "ha_entity_count": len(ha_entities),
        "ha_entity_unique_ids": [e.unique_id for e in ha_entities],
        "online": online_value,
        "reported_state_keys": sorted(reported.keys()),
        "last_sync_at": last_sync_ts,
        "seconds_since_last_sync": _seconds_since(last_sync_ts),
        # Integration-wide context — helps the user correlate a device
        # problem with a bridge-level outage.
        "ws_connected": coord.ws_connected,
        "last_ws_message_at": coord.last_ws_message_at,
        "last_polling_at": coord.last_polling_at,
        "error_count": coord.error_count,
        "companion_expires_at": getattr(coord.auth_manager, "companion_expires_at", None),
        "sberid_expires_at": getattr(coord.auth_manager, "sberid_expires_at", None),
    }


# ---------------------------------------------------------------------------
# Per-device rules
# ---------------------------------------------------------------------------


def _rule_not_in_tree(summary: dict[str, Any]) -> Finding | None:
    if summary["in_tree"]:
        return None
    return Finding(
        code="not_in_tree",
        severity="error",
        title="Sber cloud does not return this device",
        detail=(
            "The polling tree from /device_groups/tree did not include "
            "this device_id.  Either it was removed in the Sber app, it "
            "doesn't belong to this account, or the tree fetch failed."
        ),
        action=(
            "Verify the device is linked in the Sber SmartHome app.  Use "
            "the Settings tab to force a refresh."
        ),
    )


def _rule_not_enabled(summary: dict[str, Any]) -> Finding | None:
    if not summary["in_tree"]:
        return None  # Covered by _rule_not_in_tree.
    if summary["enabled"]:
        return None
    return Finding(
        code="not_enabled",
        severity="warning",
        title="Device is known but not enabled",
        detail=(
            "The integration sees the device, but it's not in the opt-in "
            "list — no HA entities were created for it."
        ),
        action="Enable it in the Devices tab of the SberHome panel.",
    )


def _rule_no_ha_entities(summary: dict[str, Any]) -> Finding | None:
    if not summary["enabled"] or not summary["in_tree"]:
        return None
    if summary["ha_entity_count"] > 0:
        return None
    return Finding(
        code="no_ha_entities",
        severity="warning",
        title="Device is enabled but no HA entities were created",
        detail=(
            f"The sbermap layer did not produce any entities for "
            f"image_set_type='{summary['image_set_type']}'.  This usually "
            "means the category isn't mapped yet."
        ),
        action=(
            "Open a GitHub issue with the image_set_type and the Raw "
            "payload from the Debug tab — this is the common first "
            "step for adding a new device category."
        ),
    )


def _rule_offline(summary: dict[str, Any]) -> Finding | None:
    if not summary["in_tree"]:
        return None
    if summary["online"] is False:
        return Finding(
            code="offline",
            severity="error",
            title="Device reports online=false",
            detail=(
                "Sber cloud's latest snapshot says the device is not "
                "reachable on its local network (Wi-Fi down, power "
                "outage, re-pairing needed)."
            ),
            action=(
                "Power-cycle the device and check that it's visible in the Sber SmartHome app."
            ),
        )
    return None


def _rule_stale_state(summary: dict[str, Any]) -> Finding | None:
    if not summary["in_tree"]:
        return None
    secs = summary["seconds_since_last_sync"]
    if secs is None:
        return None  # No last_sync data — can't judge.
    if secs < _STALE_WARNING_SECONDS:
        return None
    minutes = int(secs // 60)
    return Finding(
        code="stale_state",
        severity="warning",
        title=f"No fresh reported_state in {minutes} min",
        detail=(
            "The device hasn't emitted a new reported_state in a while. "
            "Sensors usually refresh at least every few minutes; a long "
            "gap often means the device is silently offline even though "
            "online=true."
        ),
        action="Check WS connectivity and the Sber app for sync status.",
    )


# ---------------------------------------------------------------------------
# Integration-wide rules (attached to every report)
# ---------------------------------------------------------------------------


def _rule_ws_disconnected(summary: dict[str, Any]) -> Finding | None:
    if summary["ws_connected"]:
        return None
    return Finding(
        code="ws_disconnected",
        severity="info",
        title="WebSocket disconnected — relying on polling",
        detail=(
            "Real-time DEVICE_STATE push is unavailable; updates arrive "
            "only on the next polling refresh.  This is fine for a brief "
            "reconnect window but means reaction latency jumps from "
            "seconds to ~30s+ while it lasts."
        ),
        action="If persistent, check Monitor tab → Status → WS error count.",
    )


def _rule_token_expiring(summary: dict[str, Any]) -> Finding | None:
    for kind in ("companion", "sberid"):
        exp = summary.get(f"{kind}_expires_at")
        if exp is None:
            continue
        remaining = exp - time.time()
        if remaining < _TOKEN_WARN_LEEWAY_SECONDS:
            hours = max(0, int(remaining // 3600))
            return Finding(
                code=f"{kind}_token_expiring",
                severity="warning",
                title=f"{kind.capitalize()} token expires in ~{hours}h",
                detail=(
                    f"The {kind} token will soon need a refresh.  HA "
                    "normally handles this automatically, but a failing "
                    "refresh will take the integration offline."
                ),
                action="Check the Diagnostics tab for recent auth errors.",
            )
    return None


def _rule_api_errors(summary: dict[str, Any]) -> Finding | None:
    count = int(summary.get("error_count") or 0)
    if count == 0:
        return None
    return Finding(
        code="api_errors_recorded",
        severity="warning" if count < 10 else "error",
        title=f"{count} API / auth error(s) since startup",
        detail=(
            "The coordinator has seen failed polling refreshes or auth "
            "problems.  A few transient errors are normal; a growing "
            "count points to a persistent network/auth problem."
        ),
        action=("Open HA logs and filter by `custom_components.sberhome` for stacktraces."),
    )


_PER_DEVICE_RULES = (
    _rule_not_in_tree,
    _rule_not_enabled,
    _rule_no_ha_entities,
    _rule_offline,
    _rule_stale_state,
)

_INTEGRATION_RULES = (
    _rule_ws_disconnected,
    _rule_token_expiring,
    _rule_api_errors,
)


def diagnose_device(coord: SberHomeCoordinator, device_id: str) -> DiagnosticReport:
    """Run every diagnostic rule against ``device_id`` and produce a report."""
    summary = _collect_summary(coord, device_id)
    findings: list[Finding] = []
    for rule in _PER_DEVICE_RULES:
        f = rule(summary)
        if f is not None:
            findings.append(f)
    for rule in _INTEGRATION_RULES:
        f = rule(summary)
        if f is not None:
            findings.append(f)

    verdict = _verdict_for([f.severity for f in findings])
    if verdict == "ok" and not findings:
        # Signal the "all clear" state explicitly so the UI shows the
        # green verdict rather than an empty list that looks unfinished.
        findings.append(
            Finding(
                code="clean",
                severity="ok",
                title="No issues detected",
                detail=(
                    "The device is in the Sber tree, enabled, mapped to "
                    "HA entities, online, with a recent reported_state.  "
                    "The integration itself is healthy."
                ),
            )
        )
    return DiagnosticReport(
        device_id=device_id,
        verdict=verdict,
        findings=findings,
        summary=summary,
    )
