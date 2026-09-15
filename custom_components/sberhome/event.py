"""SberHome event entities (scenario buttons) — sbermap PR #7 + WS push PR #11."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.const import Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .intent_dispatcher import EVENT_SBERHOME_INTENT
from .sbermap import HaEntityData

PARALLEL_UPDATES = 0
"""Без ограничения: сущности платформы берут данные у координатора и сами в облако не ходят."""


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[EventEntity] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.EVENT:
                entities.append(SberSbermapEvent(coordinator, device_id, ent))
    # Событие «сценарий сработал» — нативный HA-триггер на каждый сценарий.
    for scenario in coordinator.scenarios:
        if scenario.id and scenario.name:
            entities.append(SberScenarioEvent(coordinator, scenario.id, scenario.name))
    async_add_entities(entities)


class SberScenarioEvent(CoordinatorEntity[SberHomeCoordinator], EventEntity):
    """HA-событие: стреляет, когда облачный сценарий Sber сработал.

    Даёт «сценарий X сработал» как нативный триггер в редакторе
    автоматизаций (device trigger), без слушания сырого
    ``sberhome_intent`` в YAML. Источник — тот же event-bus
    ``{DOMAIN}_intent``, который наполняет ``intent_dispatcher`` из журнала
    сценариев Sber (``/scenario/v2/event``).
    """

    _attr_has_entity_name = True
    _attr_icon = "mdi:script-text-play-outline"
    _attr_event_types = ["triggered"]

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        scenario_id: str,
        scenario_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._scenario_id = scenario_id
        self._attr_name = scenario_name
        self._attr_unique_id = f"sberhome_scenario_event_{scenario_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    def _scenario(self):
        return next((s for s in self.coordinator.scenarios if s.id == self._scenario_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._scenario() is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_SBERHOME_INTENT, self._handle_intent_event)
        )

    @callback
    def _handle_intent_event(self, event: Event) -> None:
        """Fire HA-событие, если сработал ИМЕННО этот сценарий.

        ``intent_dispatcher`` шлёт базовое событие (``slug=None``) и по
        одному на каждый matching listener (``slug=<slug>``). Берём только
        базовое, чтобы не стрелять дважды.
        """
        data = event.data or {}
        if data.get("slug") is not None:
            return
        if data.get("scenario_id") != self._scenario_id:
            return
        self._trigger_event(
            "triggered",
            {
                "name": data.get("name"),
                "type": data.get("type"),
                "trigger_type": data.get("trigger_type"),
                "event_time": data.get("event_time"),
            },
        )
        self.async_write_ha_state()


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
            ha_entity.unique_id[len(prefix) :] if ha_entity.unique_id.startswith(prefix) else ""
        )
        super().__init__(coordinator, device_id, suffix)
        self._ha_unique_id = ha_entity.unique_id
        self._state_key = ha_entity.state_attribute_key or ""
        self._attr_event_types = list(ha_entity.event_types or ())
        # Нажатие, которое уже лежит в reported_state при создании сущности
        # (запуск HA, перезагрузка записи после смены выбора устройств), —
        # прошлое, а не новое: без этой отметки первое же обновление
        # координатора повторяло его как событие и запускало автоматизации.
        current = self._current_press()
        self._last_seen: str | None = current[1] if current else None

    def _current_press(self) -> tuple[str, str] | None:
        """Текущее нажатие: ``(тип события, отметка)``.

        Отметка — тип вместе со временем синхронизации атрибута, если оно
        есть: так повторное нажатие того же типа отличается от прежнего.
        """
        ent = self._entity_data(self._ha_unique_id)
        if ent is None or ent.state is None:
            return None
        value = str(ent.state)
        # Используем raw timestamp из reported_state если есть.
        ts = None
        dto = self._device_dto
        if dto is not None:
            for av in dto.reported_state:
                if av.key == self._state_key:
                    ts = getattr(av, "last_sync", None)
                    break
        return value, (f"{value}:{ts}" if ts else value)

    @callback
    def _handle_coordinator_update(self) -> None:
        current = self._current_press()
        if current is not None and current[1] != self._last_seen:
            value, self._last_seen = current
            if value in self._attr_event_types:
                self._trigger_event(value)
        super()._handle_coordinator_update()
