"""Support for SberHome select entities (enum-настройки)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_SELECTS, SelectSpec, resolve_category
from .utils import find_from_list


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericSelect] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        for spec in CATEGORY_SELECTS.get(category, []):
            # Создаём только если feature объявлена в attributes (устройство её поддерживает).
            if _has_attribute(device, spec.key):
                entities.append(SberGenericSelect(coordinator, device_id, spec))
    async_add_entities(entities)


def _has_attribute(device: dict, key: str) -> bool:
    """Feature объявлена у устройства через attributes ИЛИ присутствует
    в reported/desired_state (устройство реально репортит эту фичу)."""
    for section in ("attributes", "reported_state", "desired_state"):
        if section in device and find_from_list(device[section], key) is not None:
            return True
    return False


class SberGenericSelect(SberBaseEntity, SelectEntity):
    """Универсальный select через SelectSpec."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: SelectSpec,
    ) -> None:
        super().__init__(coordinator, device_id, spec.suffix)
        self._spec = spec
        self._attr_options = list(spec.options)
        if spec.entity_category is not None:
            self._attr_entity_category = spec.entity_category
        if spec.icon is not None:
            self._attr_icon = spec.icon

    @property
    def current_option(self) -> str | None:
        state = self._get_desired_state(self._spec.key)
        if state and "enum_value" in state:
            value = state["enum_value"]
            return value if value in self._attr_options else None
        return None

    async def async_select_option(self, option: str) -> None:
        await self._async_send_states(
            [{"key": self._spec.key, "enum_value": option}]
        )
