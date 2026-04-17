"""Scenario DTOs.

ScenarioWidgetDto — WS push виджеты (topic SCENARIO_WIDGETS).
ScenarioDto — сценарий v2 из REST API (GET /scenario/v2/scenario).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class ScenarioWidgetDto:
    """Виджет сценария из WS push.

    Минимальная типизация — полная структура содержит множество
    вложенных полей, которые пока не используются интеграцией.
    """

    id: str | None = None
    name: str | None = None
    type: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class ScenarioDto:
    """Сценарий Sber v2 — REST API ``/scenario/v2/scenario``.

    ``triggers`` и ``actions`` — сложные вложенные структуры, оставлены
    как list[dict] для гибкости (shape зависит от типа trigger/action).
    """

    id: str | None = None
    name: str | None = None
    type: str | None = None
    enabled: bool | None = None
    triggers: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["ScenarioDto", "ScenarioWidgetDto"]
