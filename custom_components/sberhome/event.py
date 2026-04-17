"""SberHome event entities (scenario buttons) — sbermap PR #7 + WS push PR #11."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SIGNAL_DEVMAN_EVENT, SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapEvent] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.EVENT:
                entities.append(SberSbermapEvent(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapEvent(SberBaseEntity, EventEntity):
    """Scenario button event — fired on state change."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        ha_entity: HaEntityData,
    ) -> None:
        dto = coordinator.devices.get(device_id)
        device_real_id = (dto.id if dto else None) or device_id
        prefix = f"{device_real_id}_"
        suffix = (
            ha_entity.unique_id[len(prefix):]
            if ha_entity.unique_id.startswith(prefix)
            else ""
        )
        super().__init__(coordinator, device_id, suffix)
        self._ha_unique_id = ha_entity.unique_id
        self._state_key = ha_entity.state_attribute_key or ""
        self._attr_event_types = list(ha_entity.event_types or ())
        self._last_seen: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        ent = self._entity_data(self._ha_unique_id)
        if ent is not None and ent.state is not None:
            value = str(ent.state)
            # Используем raw timestamp из reported_state если есть.
            ts = None
            dto = self._device_dto
            if dto is not None:
                for av in dto.reported_state:
                    if av.key == self._state_key:
                        ts = getattr(av, "last_sync", None)
                        break
            marker = f"{value}:{ts}" if ts else value
            if marker != self._last_seen:
                self._last_seen = marker
                if value in self._attr_event_types:
                    self._trigger_event(value)
        super()._handle_coordinator_update()

    async def async_added_to_hass(self) -> None:
        """Подписаться на dispatcher для DEVMAN_EVENT WS push'ей (PR #11).

        Coordinator получает WS event'ы и шлёт через `SIGNAL_DEVMAN_EVENT`.
        Event entity слушает signal и стреляет в HA event bus в реальном
        времени (без ожидания polling tick).
        """
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_DEVMAN_EVENT, self._handle_devman_signal
            )
        )

    @callback
    def _handle_devman_signal(
        self, device_id: str | None, event_payload: dict[str, Any]
    ) -> None:
        """Обработать WS DEVMAN_EVENT — fire HA event если совпадает device + key.

        Sber payload в `event` обычно содержит `key` (= state_attribute_key типа
        "button_1_event") и `enum_value` (= тип события "click"/"double_click").
        Точная схема может варьироваться — ловим оба варианта.
        """
        if device_id != self._device_id:
            return
        if not isinstance(event_payload, dict):
            return
        key = event_payload.get("key")
        if key != self._state_key:
            return
        value = event_payload.get("enum_value") or event_payload.get("value")
        if value and value in self._attr_event_types:
            self._trigger_event(str(value))
            self.async_write_ha_state()
