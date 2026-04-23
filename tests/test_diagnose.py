"""Unit tests for the per-device diagnostic advisor.

The advisor is a pure reducer over coordinator state — breakage here
silently lies to the user ("no issues detected" when the device is
dead, or "broken" for a healthy device).  These tests pin each rule
individually and the verdict aggregation.
"""

from __future__ import annotations

import time
from datetime import UTC
from unittest.mock import MagicMock

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.dto.values import (
    AttributeValueDto,
    AttributeValueType,
)
from custom_components.sberhome.diagnose import (
    DiagnosticReport,
    Finding,
    diagnose_device,
)


def _coord(
    *,
    in_tree: bool = True,
    enabled: bool = True,
    ha_entities: int = 1,
    online: bool | None = True,
    last_sync: str | None = None,
    ws_connected: bool = True,
    error_count: int = 0,
    companion_expires_at: float | None = None,
    sberid_expires_at: float | None = None,
) -> MagicMock:
    coord = MagicMock()
    reported: list[AttributeValueDto] = []
    if online is not None:
        reported.append(
            AttributeValueDto(
                key="online",
                type=AttributeValueType.BOOL,
                bool_value=online,
                last_sync=last_sync,
            )
        )
    dto = DeviceDto(
        id="dev-1",
        image_set_type="cat_light_basic",
        reported_state=reported,
    )
    if in_tree:
        coord.state_cache.get_device = MagicMock(return_value=dto)
        coord.state_cache.get_all_devices = MagicMock(return_value={"dev-1": dto})
    else:
        coord.state_cache.get_device = MagicMock(return_value=None)
    coord.enabled_device_ids = {"dev-1"} if enabled else set()
    # The advisor reads ``e.unique_id`` for the summary, so configure
    # MagicMocks with a real string attribute (not a nested MagicMock).
    entity_list = []
    for i in range(ha_entities):
        e = MagicMock()
        e.unique_id = f"dev-1_entity_{i}"
        entity_list.append(e)
    coord.entities = {"dev-1": entity_list}
    coord.ws_connected = ws_connected
    coord.error_count = error_count
    coord.last_ws_message_at = None
    coord.last_polling_at = None
    auth = MagicMock()
    auth.companion_expires_at = companion_expires_at
    auth.sberid_expires_at = sberid_expires_at
    coord.auth_manager = auth
    return coord


class TestPerDeviceRules:
    def test_clean_device_gets_ok_verdict(self) -> None:
        report = diagnose_device(_coord(), "dev-1")
        # Green path must surface an explicit "clean" finding —
        # otherwise the UI shows an empty list that looks unfinished.
        assert report.verdict == "ok"
        assert any(f.code == "clean" for f in report.findings)

    def test_missing_device_is_error(self) -> None:
        report = diagnose_device(_coord(in_tree=False, enabled=False), "dev-1")
        codes = {f.code for f in report.findings}
        assert "not_in_tree" in codes
        assert report.verdict == "broken"

    def test_disabled_device_is_warning(self) -> None:
        report = diagnose_device(_coord(enabled=False, ha_entities=0), "dev-1")
        codes = {f.code for f in report.findings}
        assert "not_enabled" in codes
        # Not "broken" — user intentionally skipped opt-in.
        assert report.verdict == "warning"

    def test_no_ha_entities_surfaces_warning(self) -> None:
        # Device is enabled but the mapper produced zero entities —
        # usually an unmapped image_set_type.
        report = diagnose_device(_coord(ha_entities=0), "dev-1")
        codes = {f.code for f in report.findings}
        assert "no_ha_entities" in codes

    def test_offline_device_is_error_with_actionable_hint(self) -> None:
        report = diagnose_device(_coord(online=False), "dev-1")
        finding = next(f for f in report.findings if f.code == "offline")
        assert finding.severity == "error"
        # Action must be concrete, not "something is wrong".
        assert finding.action

    def test_stale_state_is_warning(self) -> None:
        # last_sync far in the past → stale_state fires.
        old_iso = "2024-01-01T00:00:00Z"
        report = diagnose_device(_coord(last_sync=old_iso), "dev-1")
        assert any(f.code == "stale_state" for f in report.findings)

    def test_fresh_state_no_stale_warning(self) -> None:
        from datetime import datetime

        # Recent last_sync → no stale warning.
        fresh = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        report = diagnose_device(_coord(last_sync=fresh), "dev-1")
        assert not any(f.code == "stale_state" for f in report.findings)


class TestIntegrationWideRules:
    """Rules that tag every report, not just the device."""

    def test_ws_disconnected_becomes_info_finding(self) -> None:
        report = diagnose_device(_coord(ws_connected=False), "dev-1")
        finding = next(f for f in report.findings if f.code == "ws_disconnected")
        # Info, not error — polling fallback still works.
        assert finding.severity == "info"

    def test_token_expiring_soon_is_warning(self) -> None:
        # Expires in 12 hours → warning (threshold is 24h).
        soon = time.time() + 12 * 3600
        report = diagnose_device(_coord(companion_expires_at=soon), "dev-1")
        assert any(
            f.code == "companion_token_expiring" and f.severity == "warning"
            for f in report.findings
        )

    def test_token_far_in_future_no_warning(self) -> None:
        far = time.time() + 30 * 24 * 3600
        report = diagnose_device(_coord(companion_expires_at=far), "dev-1")
        assert not any("token_expiring" in f.code for f in report.findings)

    def test_many_errors_escalate_to_error_severity(self) -> None:
        # A handful of errors is warning; a lot escalates to error.
        report = diagnose_device(_coord(error_count=25), "dev-1")
        finding = next(f for f in report.findings if f.code == "api_errors_recorded")
        assert finding.severity == "error"
        assert "25" in finding.title


class TestVerdictAggregation:
    def test_verdict_picks_worst_severity(self) -> None:
        # Mix of error + info must still produce "broken".
        report = diagnose_device(_coord(online=False, ws_connected=False), "dev-1")
        assert report.verdict == "broken"


class TestSerialization:
    def test_report_is_json_serializable(self) -> None:
        import json

        report = diagnose_device(_coord(), "dev-1")
        data = json.dumps(report.as_dict())
        # Field names read directly by the UI — renames silently break it.
        for field_name in ("verdict", "findings", "summary", "severity"):
            assert f'"{field_name}"' in data

    def test_finding_has_expected_fields(self) -> None:
        f = Finding(code="x", severity="info", title="t", detail="d")
        assert set(f.as_dict().keys()) == {"code", "severity", "title", "detail", "action"}


class TestReportDataclass:
    def test_construct_empty_and_serialize(self) -> None:
        r = DiagnosticReport(device_id="x", verdict="ok")
        assert r.as_dict() == {
            "device_id": "x",
            "verdict": "ok",
            "findings": [],
            "summary": {},
        }
