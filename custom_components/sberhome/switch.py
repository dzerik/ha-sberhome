"""Support for SberHome switches — sbermap-driven (PR #4 + bidirectional PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON, EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aiosber.dto.union import UnionType
from .const import DOMAIN
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_switch_command
from .staros_settings_entity import SberStarosSettingBase
from .switch_groups import SberGroupSwitch


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
    for home in coordinator.homes:
        entities.append(SberAtHomeSwitch(coordinator, home["id"], home["name"]))
    # Sber custom-groups (group_type=GROUP) как bulk-switch entities.
    # Группы без devices пропускаются — не создаём пустых toggle'ов.
    for group_id, group in coordinator.state_cache.get_all_groups().items():
        if group.group_type != UnionType.GROUP:
            continue
        if not coordinator.state_cache.get_group_devices(group_id):
            continue
        entities.append(SberGroupSwitch(coordinator, group_id))
    # Настройки-тумблеры умных колонок Сбера (детский режим, звуки и т.п.).
    for specs in coordinator.staros_settings_entities.values():
        for spec in specs:
            if spec.platform is Platform.SWITCH:
                entities.append(SberStarosSettingSwitch(coordinator, spec))
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
    """Writable switch переменной at_home КОНКРЕТНОГО дома Sber.

    Один entity на дом (у аккаунта может быть несколько домов, и значение
    «я дома» у каждого своё). Позволяет HA-автоматизациям менять at_home
    нужного дома (например «когда кто-то пришёл на дачу → включить at_home
    дачи, что триггерит сберовский сценарий»).
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:home-account"

    def __init__(self, coordinator: SberHomeCoordinator, home_id: str, home_name: str) -> None:
        super().__init__(coordinator)
        self._home_id = home_id
        self._attr_name = f"At home ({home_name})"
        self._attr_unique_id = f"sberhome_at_home_{home_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    @property
    def available(self) -> bool:
        return self._home_id in self.coordinator.at_home

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.at_home.get(self._home_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_at_home(True, self._home_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_at_home(False, self._home_id)


class SberStarosSettingSwitch(SberStarosSettingBase, SwitchEntity):
    """Настройка-тумблер умной колонки Сбера."""

    @property
    def is_on(self) -> bool | None:
        spec = self._current()
        if spec is None:
            return None
        return spec.state == STATE_ON

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_write(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_write(False)
