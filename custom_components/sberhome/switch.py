"""Support for SberHome switches — sbermap-driven (PR #4 + bidirectional PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_ON, EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .action_errors import async_translate_cloud_errors
from .aiosber.dto.union import UnionType
from .const import DOMAIN
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_switch_command
from .staros_settings_entity import SberStarosSettingBase
from .switch_groups import SberGroupSwitch

PARALLEL_UPDATES = 1
"""Команды сущностей платформы уходят в облако Сбера по одной.

Облако одно на весь аккаунт и на всплеск запросов отвечает 429; опрос состояния
идёт через координатор и этим ограничением не задерживается.
"""


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
    for specs in coordinator.staros_settings_entities.values():
        for spec in specs:
            if spec.platform is Platform.SWITCH:
                entities.append(SberStarosSettingSwitch(coordinator, spec))
    async_add_entities(entities)
    known: set[tuple[str, str]] = set()

    @callback
    def discover_automation_switches() -> None:
        added: list[SwitchEntity] = []
        for home in coordinator.homes:
            key = ("home", home["id"])
            if key not in known:
                known.add(key)
                added.append(SberAtHomeSwitch(coordinator, home["id"], home["name"]))
        for scenario in coordinator.scenarios:
            if not scenario.id or not scenario.name:
                continue
            key = ("scenario", scenario.id)
            if key not in known:
                known.add(key)
                added.append(SberScenarioActiveSwitch(coordinator, scenario.id, scenario.name))
        for group_id, group in coordinator.state_cache.get_all_groups().items():
            key = ("group", group_id)
            if (
                key not in known
                and group.group_type == UnionType.GROUP
                and coordinator.state_cache.get_group_devices(group_id)
            ):
                known.add(key)
                added.append(SberGroupSwitch(coordinator, group_id))
        if added:
            async_add_entities(added)

    discover_automation_switches()
    entry.async_on_unload(coordinator.async_add_listener(discover_automation_switches))


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
        self._attr_translation_key = "at_home"
        self._attr_translation_placeholders = {"name": home_name}
        self._attr_unique_id = f"sberhome_at_home_{home_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        home = next((h for h in self.coordinator.homes if h["id"] == self._home_id), None)
        if home is not None:
            placeholders = {"name": home["name"]}
            if self.translation_placeholders != placeholders:
                self._attr_translation_placeholders = placeholders
                self.__dict__.pop("name", None)
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        return super().available and self._home_id in self.coordinator.at_home

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.at_home.get(self._home_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        async with async_translate_cloud_errors(self.coordinator, refresh_scenarios=True):
            await self.coordinator.async_set_at_home(True, self._home_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        async with async_translate_cloud_errors(self.coordinator, refresh_scenarios=True):
            await self.coordinator.async_set_at_home(False, self._home_id)


class SberScenarioActiveSwitch(CoordinatorEntity[SberHomeCoordinator], SwitchEntity):
    """Тумблер автосрабатывания облачного сценария Sber (`is_active`).

    On/off меняет, срабатывает ли сценарий по своему триггеру (фраза,
    датчик, расписание). Запуск сценария «прямо сейчас» — отдельная
    кнопка `button` (см. button.py). Все сценарии — в device 'Sber Scenarios'.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:calendar-check"

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        scenario_id: str,
        scenario_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._scenario_id = scenario_id
        self._attr_name = scenario_name
        self._attr_unique_id = f"sberhome_scenario_active_{scenario_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        scenario = self._scenario()
        if scenario is not None and scenario.name:
            self._attr_name = scenario.name
        super()._handle_coordinator_update()

    def _scenario(self):
        return next((s for s in self.coordinator.scenarios if s.id == self._scenario_id), None)

    @property
    def available(self) -> bool:
        return super().available and self._scenario() is not None

    @property
    def is_on(self) -> bool | None:
        scenario = self._scenario()
        return scenario.is_active if scenario else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        async with async_translate_cloud_errors(self.coordinator, refresh_scenarios=True):
            await self.coordinator.async_set_scenario_active(self._scenario_id, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        async with async_translate_cloud_errors(self.coordinator, refresh_scenarios=True):
            await self.coordinator.async_set_scenario_active(self._scenario_id, False)


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
