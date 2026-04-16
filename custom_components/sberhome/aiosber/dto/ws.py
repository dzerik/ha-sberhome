"""WebSocket-сообщение SocketMessageDto.

Источник: `ru.sberdevices.smarthome.gateway.impl.domain.websocket.dto.SocketMessageDto`.

В JSON приходит объект, в котором заполнено только ОДНО из полей —
по этому полю определяется тип события (см. `topic` property и `Topic` enum).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .enums import Topic
from .state import StateDto


@dataclass(slots=True, frozen=True)
class SocketMessageDto:
    """Универсальное WS-сообщение.

    Парсится через from_dict — затем используй `.topic` для диспетчеризации.

    Для большинства полей мы оставляем сырой dict (Any), потому что Sber
    использует там сложные nested структуры, которые редко нужны интеграции
    HA. Главное (DEVICE_STATE) распарсено в StateDto.

    `device_id`/`id` — Sber кладёт ID устройства на верхний уровень payload
    (имя поля варьируется между топиками). Хелпер `target_device_id`
    возвращает первое непустое значение.
    """

    state: StateDto | None = None
    fw_task_status: dict[str, Any] | None = None  # OtaUpdateInfoDto
    scenario_widget: dict[str, Any] | None = None  # ScenarioWidgetDto
    scenario_home_change_variable: dict[str, Any] | None = None
    home_widget: dict[str, Any] | None = None  # SmartHomeCategoryDataDto
    event: dict[str, Any] | None = None  # DevmanDto (button events, alarms)
    group_state: dict[str, Any] | None = None  # GroupStateDto
    home_transfer: dict[str, Any] | None = None  # HomeTransferBaseDto
    device_id: str | None = None
    id: str | None = None

    @property
    def target_device_id(self) -> str | None:
        """Первое непустое из device_id / id / event['device_id']."""
        if self.device_id:
            return self.device_id
        if self.id:
            return self.id
        if self.event and isinstance(self.event, dict):
            ev_id = self.event.get("device_id") or self.event.get("id")
            if ev_id:
                return str(ev_id)
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
