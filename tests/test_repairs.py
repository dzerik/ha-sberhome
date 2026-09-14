"""Repairs, выводимые из здоровья интеграции."""

from __future__ import annotations

from types import SimpleNamespace

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.repairs import (
    UPDATE_FAILING_THRESHOLD,
    async_update_repair_issues,
    collect_health_inputs,
)


def _coord(**overrides) -> SimpleNamespace:
    base = {
        "last_update_success": True,
        "ws_connected": True,
        "consecutive_failures": 0,
        "last_error": None,
        "auth_manager": SimpleNamespace(companion_expires_at=None),
        "enabled_device_uids": None,
        "enabled_device_ids": None,
        "registry_maintenance_failures": 0,
        "disabled_background_polls": lambda: [],
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_collect_reads_the_coordinator(hass: HomeAssistant) -> None:
    coord = _coord(
        ws_connected=False,
        auth_manager=SimpleNamespace(companion_expires_at=123.0, sberid_expires_at=None),
        enabled_device_uids=["a", "b", "c"],
        enabled_device_ids={"a"},
        disabled_background_polls=lambda: ["OTA"],
    )
    inputs = collect_health_inputs(hass, coord, now=100.0)
    assert inputs.ws_connected is False
    assert inputs.token_expiries == {"companion": 123.0, "sberid": None, "smart_home": None}
    assert inputs.unresolved_selection == 2
    assert inputs.disabled_polls == ["OTA"]


async def test_repeated_update_failures_raise_an_issue_until_recovery(hass: HomeAssistant) -> None:
    registry = ir.async_get(hass)
    failing = _coord(
        last_update_success=False,
        consecutive_failures=UPDATE_FAILING_THRESHOLD,
        last_error={"kind": "SberConnectionError", "message": "timeout", "at": 1.0},
    )
    async_update_repair_issues(hass, failing)
    issue = registry.async_get_issue(DOMAIN, "update_failing")
    assert issue.severity == ir.IssueSeverity.ERROR
    assert issue.translation_placeholders == {
        "count": str(UPDATE_FAILING_THRESHOLD),
        "error": "SberConnectionError: timeout",
    }

    async_update_repair_issues(hass, _coord())
    assert registry.async_get_issue(DOMAIN, "update_failing") is None


async def test_a_single_failure_is_not_worth_a_repair(hass: HomeAssistant) -> None:
    async_update_repair_issues(hass, _coord(last_update_success=False, consecutive_failures=1))
    assert ir.async_get(hass).async_get_issue(DOMAIN, "update_failing") is None


async def test_disabled_background_poll_issue(hass: HomeAssistant) -> None:
    registry = ir.async_get(hass)
    async_update_repair_issues(hass, _coord(disabled_background_polls=lambda: ["Scenario", "OTA"]))
    issue = registry.async_get_issue(DOMAIN, "background_poll_disabled")
    assert issue.severity == ir.IssueSeverity.WARNING
    assert issue.translation_placeholders == {"polls": "Scenario, OTA"}
    async_update_repair_issues(hass, _coord())
    assert registry.async_get_issue(DOMAIN, "background_poll_disabled") is None


def test_issue_texts_exist_in_every_language() -> None:
    import json
    from pathlib import Path

    base = Path(__file__).resolve().parents[1] / "custom_components" / "sberhome"
    files = [base / "strings.json", *sorted((base / "translations").glob("*.json"))]
    for path in files:
        issues = json.loads(path.read_text(encoding="utf-8"))["issues"]
        assert "{count}" in issues["update_failing"]["description"], path.name
        assert "{error}" in issues["update_failing"]["description"], path.name
        assert "{polls}" in issues["background_poll_disabled"]["description"], path.name
