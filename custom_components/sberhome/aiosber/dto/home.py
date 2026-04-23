"""HomeChangeVariableDto — изменение домашней переменной.

JSON schema: поле ``scenario_home_change_variable`` в SocketMessageDto
(WS topic SCENARIO_HOME_CHANGE_VARIABLE).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class HomeChangeVariableDto:
    """Изменение домашней переменной из WS push.

    ``variable`` оставлен как dict — внутренняя структура HomeVariableDto
    варьируется.
    """

    change_type: str | None = None
    id: str | None = None
    variable: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        # uses camelCase: changeType
        if isinstance(data, dict) and "changeType" in data and "change_type" not in data:
            data = {**data, "change_type": data["changeType"]}
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["HomeChangeVariableDto"]
