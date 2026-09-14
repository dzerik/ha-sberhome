"""Оценка здоровья интеграции для панели и Repairs.

Раньше статус показывал набор счётчиков, из которого пользователь сам
должен был понять, всё ли в порядке: «ошибок за сессию 3» одинаково
выглядело и при единичной DNS-икоте час назад, и при облаке, которое не
отвечает прямо сейчас. Оценка сводит состояние к healthy / degraded /
unhealthy и перечисляет причины кодами, которые панель локализует.
"""

from __future__ import annotations

from custom_components.sberhome.health import HealthInputs, compute_health

NOW = 1_000_000.0
DAY = 86_400


def _inputs(**overrides) -> HealthInputs:
    base = {
        "last_update_success": True,
        "ws_connected": True,
        "consecutive_failures": 0,
        "token_expiries": {"companion": NOW + 7 * DAY},
        "disabled_polls": [],
        "unresolved_selection": 0,
        "conflicts": [],
        "registry_failures": 0,
        "now": NOW,
    }
    base.update(overrides)
    return HealthInputs(**base)


def _codes(result) -> list[str]:
    return [issue["code"] for issue in result["issues"]]


def test_all_good_is_healthy() -> None:
    result = compute_health(_inputs())
    assert result == {"score": "healthy", "issues": []}


def test_failing_updates_are_unhealthy() -> None:
    result = compute_health(_inputs(last_update_success=False, consecutive_failures=3))
    assert result["score"] == "unhealthy"
    assert result["issues"][0] == {
        "code": "update_failing",
        "severity": "error",
        "params": {"count": 3},
    }


def test_ws_down_while_polling_works_is_degraded() -> None:
    result = compute_health(_inputs(ws_connected=False))
    assert result["score"] == "degraded"
    assert _codes(result) == ["ws_disconnected"]


def test_token_that_refreshes_itself_is_not_a_problem() -> None:
    """Companion живёт около часа и сам обновляется — это не повод для тревоги."""
    result = compute_health(_inputs(token_expiries={"companion": NOW + 3600, "sberid": NOW + 60}))
    assert result == {"score": "healthy", "issues": []}


def test_token_expiring_within_a_day_is_degraded() -> None:
    result = compute_health(
        _inputs(token_expiries={"companion": NOW + 3600, "sberid": None}, tokens_refreshable=False)
    )
    assert result["score"] == "degraded"
    assert result["issues"] == [
        {
            "code": "token_expiring",
            "severity": "warning",
            "params": {"token": "companion", "hours": 1},
        }
    ]


def test_already_expired_token_reads_zero_hours() -> None:
    result = compute_health(_inputs(token_expiries={"sberid": NOW - 10}, tokens_refreshable=False))
    assert result["issues"][0]["params"] == {"token": "sberid", "hours": 0}


def test_every_warning_is_listed() -> None:
    result = compute_health(
        _inputs(
            ws_connected=False,
            disabled_polls=["Scenario", "OTA"],
            unresolved_selection=2,
            conflicts=["sberdevices"],
            registry_failures=1,
        )
    )
    assert result["score"] == "degraded"
    assert _codes(result) == [
        "ws_disconnected",
        "background_poll_disabled",
        "selection_unresolved",
        "conflicting_integration",
        "registry_maintenance_failed",
    ]
    by_code = {i["code"]: i["params"] for i in result["issues"]}
    assert by_code["background_poll_disabled"] == {"polls": "Scenario, OTA"}
    assert by_code["selection_unresolved"] == {"count": 2}


def test_errors_come_before_warnings() -> None:
    result = compute_health(
        _inputs(ws_connected=False, last_update_success=False, consecutive_failures=1)
    )
    assert _codes(result) == ["update_failing", "ws_disconnected"]
    assert result["score"] == "unhealthy"
