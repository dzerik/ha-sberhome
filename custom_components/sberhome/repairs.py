"""Repairs, выводимые из здоровья интеграции.

Здесь же собираются входные данные для :func:`health.compute_health` —
WS-команда статуса и Repairs должны видеть одно и то же состояние.
"""

from __future__ import annotations

import time
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir

from .conflict import detect_conflicts
from .const import DOMAIN
from .health import HealthInputs

UPDATE_FAILING_THRESHOLD = 5
"""Столько неудачных обновлений подряд превращаются в Repairs-замечание.

Одиночный сбой сети или облака проходит сам и не стоит отдельного
уведомления — HA и так пометит сущности недоступными."""

_TOKENS = ("companion", "sberid", "smart_home")


def collect_health_inputs(
    hass: HomeAssistant, coord: Any, *, now: float | None = None
) -> HealthInputs:
    """Снять с координатора срез, из которого считается здоровье.

    Args:
        hass: Home Assistant — нужен для поиска конфликтующих интеграций.
        coord: Координатор SberHome.
        now: Текущее время (для тестов); по умолчанию ``time.time()``.

    Returns:
        Входные данные для :func:`health.compute_health`.
    """
    auth = coord.auth_manager
    stored = coord.enabled_device_uids
    resolved = coord.enabled_device_ids or set()
    return HealthInputs(
        last_update_success=bool(coord.last_update_success),
        ws_connected=bool(coord.ws_connected),
        consecutive_failures=int(getattr(coord, "consecutive_failures", 0)),
        token_expiries={name: getattr(auth, f"{name}_expires_at", None) for name in _TOKENS},
        disabled_polls=list(coord.disabled_background_polls()),
        unresolved_selection=max(len(stored) - len(resolved), 0) if stored is not None else 0,
        conflicts=detect_conflicts(hass),
        registry_failures=int(getattr(coord, "registry_maintenance_failures", 0)),
        now=time.time() if now is None else now,
    )


@callback
def async_update_repair_issues(hass: HomeAssistant, coord: Any) -> None:
    """Создать или снять Repairs-замечания по текущему состоянию координатора.

    Args:
        hass: Home Assistant.
        coord: Координатор SberHome.
    """
    failures = int(getattr(coord, "consecutive_failures", 0))
    if not coord.last_update_success and failures >= UPDATE_FAILING_THRESHOLD:
        last = coord.last_error or {}
        ir.async_create_issue(
            hass,
            DOMAIN,
            "update_failing",
            is_fixable=False,
            severity=ir.IssueSeverity.ERROR,
            translation_key="update_failing",
            translation_placeholders={
                "count": str(failures),
                "error": f"{last.get('kind', '?')}: {last.get('message', '')}",
            },
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "update_failing")

    polls = coord.disabled_background_polls()
    if polls:
        ir.async_create_issue(
            hass,
            DOMAIN,
            "background_poll_disabled",
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="background_poll_disabled",
            translation_placeholders={"polls": ", ".join(polls)},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, "background_poll_disabled")
