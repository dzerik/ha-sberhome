"""Support for SberHome switches — sbermap-driven (PR #4 + bidirectional PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_switch_command


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SwitchEntity] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.SWITCH:
                entities.append(SberSbermapSwitch(coordinator, device_id, ent))
    entities.append(SberAtHomeSwitch(coordinator))
    async_add_entities(entities)


class SberSbermapSwitch(SberBaseEntity, SwitchEntity):
    """Universal switch — primary on_off + extra-switches."""

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
        self._state_key = ha_entity.state_attribute_key or "on_off"
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon

    @property
    def is_on(self) -> bool | None:
        ent = self._entity_data(self._ha_unique_id)
        if ent is None:
            return None
        if ent.state == "on":
            return True
        if ent.state == "off":
            return False
        return None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_switch_command(device_id=self._device_id, state_key=self._state_key, is_on=True)
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_switch_command(device_id=self._device_id, state_key=self._state_key, is_on=False)
        )


class SberAtHomeSwitch(CoordinatorEntity[SberHomeCoordinator], SwitchEntity):
    """Writable switch для глобальной at_home переменной Sber.

    Парный к `binary_sensor.sber_at_home` (read-only). Этот entity
    позволяет HA-автоматизациям менять значение at_home (например
    «when someone arrives → turn on at_home, which triggers Sber-сценарий
    welcome»).
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:home-account"
    _attr_name = "At home"
    _attr_unique_id = "sberhome_at_home_switch"

    def __init__(self, coordinator: SberHomeCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.at_home is not None

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.at_home

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_at_home(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_at_home(False)
