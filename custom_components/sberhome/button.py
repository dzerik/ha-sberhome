"""Support for SberHome buttons — sbermap-driven (PR #7 + PR #9)."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_button_press_command


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapButton] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.BUTTON:
                entities.append(SberSbermapButton(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapButton(SberBaseEntity, ButtonEntity):
    """Fire-and-forget action button (intercom unlock/reject_call)."""

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
        self._state_key = ha_entity.state_attribute_key or ""
        self._command_value = ha_entity.command_value
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category

    async def async_press(self) -> None:
        await self._async_send_bundle(
            build_button_press_command(
                device_id=self._device_id,
                key=self._state_key,
                command_value=self._command_value,
            )
        )
