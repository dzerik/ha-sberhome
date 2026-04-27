"""Support for SberHome select entities — sbermap-driven (PR #7 + PR #9)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_select_command


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapSelect] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.SELECT:
                entities.append(SberSbermapSelect(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapSelect(SberBaseEntity, SelectEntity):
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
        options = list(ha_entity.options or ())
        # Fallback: если spec не дал options (Sber иногда отдаёт ENUM
        # без enum_values), берём их из кэша /devices/enums по
        # attribute_key. Кэш заполняется однократно при первом refresh.
        if not options and self._state_key:
            options = coordinator.enum_values_for(self._state_key)
        self._attr_options = options
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon

    @property
    def current_option(self) -> str | None:
        ent = self._entity_data(self._ha_unique_id)
        if ent is None:
            return None
        v = ent.state
        return v if v in self._attr_options else None

    async def async_select_option(self, option: str) -> None:
        await self._async_send_attrs(
            build_select_command(device_id=self._device_id, key=self._state_key, option=option)
        )
