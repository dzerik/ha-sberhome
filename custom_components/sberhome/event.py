"""Support for SberHome event entities (scenario buttons)."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_EVENTS, EventSpec, resolve_category
from .utils import find_from_list


def _has_feature(device: dict, key: str) -> bool:
    """Feature присутствует если есть в attributes ИЛИ reported_state."""
    for section in ("attributes", "reported_state"):
        if section in device and find_from_list(device[section], key) is not None:
            return True
    return False


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericEvent] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        for spec in CATEGORY_EVENTS.get(category, []):
            if _has_feature(device, spec.key):
                entities.append(SberGenericEvent(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericEvent(SberBaseEntity, EventEntity):
    """Событие нажатия кнопки сценарного выключателя."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: EventSpec,
    ) -> None:
        super().__init__(coordinator, device_id, spec.suffix)
        self._spec = spec
        self._attr_event_types = list(spec.event_types)
        self._last_seen: str | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        state = self._get_reported_state(self._spec.key)
        if state and "enum_value" in state:
            value = state["enum_value"]
            # Sber шлёт enum_value каждый раз при нажатии; HA нужен detect change.
            # timestamp тоже должен бы быть в reported_state, но если нет — кидаем по смене.
            ts = state.get("timestamp")
            marker = f"{value}:{ts}" if ts else value
            if marker != self._last_seen:
                self._last_seen = marker
                if value in self._attr_event_types:
                    self._trigger_event(value)
        super()._handle_coordinator_update()
