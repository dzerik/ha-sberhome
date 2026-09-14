"""Оценка здоровья интеграции: healthy / degraded / unhealthy с причинами.

Чистая функция без HA-зависимостей: WS-команда статуса и Repairs собирают
входные данные с координатора и получают одинаковый вердикт. Причины
отдаются кодами с параметрами, а не готовыми фразами: панель переводит их
на язык пользователя.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

TOKEN_EXPIRY_WARNING_SEC = 24 * 3600
"""Токен, истекающий раньше этого срока, считается поводом для предупреждения."""


@dataclass(frozen=True, slots=True)
class HealthInputs:
    """Срез состояния координатора, из которого выводится оценка."""

    last_update_success: bool
    ws_connected: bool
    consecutive_failures: int
    token_expiries: dict[str, float | None]
    disabled_polls: list[str] = field(default_factory=list)
    unresolved_selection: int = 0
    conflicts: list[str] = field(default_factory=list)
    registry_failures: int = 0
    now: float = 0.0


def _issue(code: str, severity: str, **params: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "params": params}


def compute_health(inputs: HealthInputs) -> dict[str, Any]:
    """Свести состояние интеграции к оценке и списку причин.

    Args:
        inputs: Срез состояния координатора.

    Returns:
        ``{"score": "healthy"|"degraded"|"unhealthy", "issues": [...]}``;
        каждая причина — ``{"code", "severity", "params"}``, ошибки первыми.
    """
    issues: list[dict[str, Any]] = []
    if not inputs.last_update_success:
        issues.append(_issue("update_failing", "error", count=inputs.consecutive_failures))
    if not inputs.ws_connected:
        issues.append(_issue("ws_disconnected", "warning"))
    for token, expires_at in inputs.token_expiries.items():
        if expires_at is None:
            continue
        left = expires_at - inputs.now
        if left < TOKEN_EXPIRY_WARNING_SEC:
            issues.append(
                _issue("token_expiring", "warning", token=token, hours=max(int(left // 3600), 0))
            )
    if inputs.disabled_polls:
        issues.append(
            _issue("background_poll_disabled", "warning", polls=", ".join(inputs.disabled_polls))
        )
    if inputs.unresolved_selection:
        issues.append(_issue("selection_unresolved", "warning", count=inputs.unresolved_selection))
    if inputs.conflicts:
        issues.append(
            _issue("conflicting_integration", "warning", domains=", ".join(inputs.conflicts))
        )
    if inputs.registry_failures:
        issues.append(
            _issue("registry_maintenance_failed", "warning", count=inputs.registry_failures)
        )

    if any(i["severity"] == "error" for i in issues):
        score = "unhealthy"
    elif issues:
        score = "degraded"
    else:
        score = "healthy"
    return {"score": score, "issues": issues}
