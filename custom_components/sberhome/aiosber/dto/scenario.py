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

    Поля соответствуют реальному ответу gateway: ``is_active`` — включён ли
    сценарий (автосрабатывание), ``is_faulty`` — есть ли проблема,
    ``image`` — иконка. ``steps`` — вложенная структура действий, оставлена
    как list[dict] (shape зависит от типа шага).
    """

    id: str | None = None
    name: str | None = None
    is_active: bool | None = None
    is_faulty: bool | None = None
    image: str | None = None
    home_id: str | None = None
    description: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class ScenarioEventDto:
    """История срабатывания сценариев — `/scenario/v2/event`.

    Wire-формат восстановлен из живого ответа Sber Gateway:

    ```json
    {
      "id": "69ef5a41c0372739c61340a6",
      "meta": {"created_at": "...", "updated_at": "...", "deleted_at": null},
      "event_time": "2026-04-27T12:44:49.430277Z",
      "object_id": "<scenario_id>",
      "object_type": "SCENARIO",
      "name": "<имя сценария>",
      "image": "https://img...",
      "description": "",
      "type": "SUCCESS",
      "account_id": "...",
      "data": {"scenario_cancel_time": null, "start_scenario_reason": null},
      "home_id": "",
      "access_level": "OWNER"
    }
    ```

    Используется HA-coordinator'ом для catch'а голосовых команд:
    при `scenario_widgets.UPDATE_WIDGETS` push'е через WS он делает
    `GET /scenario/v2/event?home_id=X&since=<last_seen>` и fire'ит
    `sberhome_intent` event для каждого нового SUCCESS'а.
    """

    id: str | None = None
    event_time: str | None = None  # ISO-8601 с микросекундами
    object_id: str | None = None  # scenario_id
    object_type: str | None = None  # обычно "SCENARIO"
    name: str | None = None  # имя сценария
    description: str | None = None
    type: str | None = None  # "SUCCESS" / другие статусы
    image: str | None = None
    account_id: str | None = None
    home_id: str | None = None
    access_level: str | None = None
    meta: dict[str, Any] | None = None
    data: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["ScenarioDto", "ScenarioEventDto", "ScenarioWidgetDto"]
