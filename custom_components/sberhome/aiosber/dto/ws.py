"""WebSocket-сообщение SocketMessageDto.

Wire: 8 полей, заполнено только ОДНО — по нему определяется тип события
(см. ``topic`` property и ``Topic`` enum).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .devman import DevmanDto
from .enums import Topic
from .group import GroupStateDto
from .home import HomeChangeVariableDto
from .ota import OtaUpdateInfoDto
from .scenario import ScenarioWidgetDto
from .state import StateDto
from .transfer import HomeTransferBaseDto


@dataclass(slots=True, frozen=True)
class SocketMessageDto:
    """Универсальное WS-сообщение.

    Парсится через from_dict — затем используй ``.topic`` для диспетчеризации.
    Все 8 полей типизированы; ``home_widget`` оставлен как dict (сложная
    структура SmartHomeCategoryDataDto, редко нужна интеграции).
    """

    state: StateDto | None = None
    fw_task_status: OtaUpdateInfoDto | None = None
    scenario_widget: ScenarioWidgetDto | None = None
    scenario_home_change_variable: HomeChangeVariableDto | None = None
    home_widget: dict[str, Any] | None = None  # SmartHomeCategoryDataDto
    event: DevmanDto | None = None
    group_state: GroupStateDto | None = None
    home_transfer: HomeTransferBaseDto | None = None

    @property
    def target_device_id(self) -> str | None:
        """Извлечь device_id из вложенного payload.

        Приоритет:
        1. state.device_id (DEVICE_STATE)
        2. event.device_id (DEVMAN_EVENT)
        3. group_state.id (GROUP_STATE)
        """
        if self.state is not None and self.state.device_id:
            return self.state.device_id
        if self.event is not None and self.event.device_id:
            return self.event.device_id
        if self.group_state is not None and self.group_state.id:
            return self.group_state.id
        return None

    @property
    def topic(self) -> Topic | None:
        """Определить тип сообщения по тому, какое поле заполнено."""
        if self.state is not None:
            return Topic.DEVICE_STATE
        if self.fw_task_status is not None:
            return Topic.INVENTORY_OTA
        if self.scenario_widget is not None:
            return Topic.SCENARIO_WIDGETS
        if self.scenario_home_change_variable is not None:
            return Topic.SCENARIO_HOME_CHANGE_VARIABLE
        if self.home_widget is not None:
            return Topic.LAUNCHER_WIDGETS
        if self.event is not None:
            return Topic.DEVMAN_EVENT
        if self.group_state is not None:
            return Topic.GROUP_STATE
        if self.home_transfer is not None:
            return Topic.HOME_TRANSFER
        return None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)
