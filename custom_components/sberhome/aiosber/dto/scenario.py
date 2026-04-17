"""ScenarioWidgetDto — виджет сценария.

Wire: поле ``scenario_widget`` в SocketMessageDto (WS topic SCENARIO_WIDGETS).
"""

from __future__ import annotations

from dataclasses import dataclass
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


__all__ = ["ScenarioWidgetDto"]
