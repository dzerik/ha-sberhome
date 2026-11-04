"""Support for SberHome buttons — sbermap-driven (PR #7 + PR #9).

Button entities:
- `SberSbermapButton` — per-device fire-and-forget actions (intercom unlock,
  reject_call, …) описанные в sbermap CategorySpec.
- `SberScenarioButton` — отдельная entity на каждый Sber-сценарий из
  ScenarioAPI; нажатие вызывает запуск сценария.
- `SberScenarioControlButton` — отдельные stop/cancel операции сценария.
"""

from __future__ import annotations

from typing import Literal

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .action_errors import async_translate_cloud_errors
from .aiosber.exceptions import ApiError
from .const import DOMAIN
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_button_press_command

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
    entities: list[ButtonEntity] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.BUTTON:
                entities.append(SberSbermapButton(coordinator, device_id, ent))
    async_add_entities(entities)
    known: set[str] = set()

    @callback
    def discover_scenarios() -> None:
        added: list[ButtonEntity] = []
        for scenario in coordinator.scenarios:
            if not scenario.id or not scenario.name or scenario.id in known:
                continue
            known.add(scenario.id)
            added.extend(
                [
                    SberScenarioButton(coordinator, scenario.id, scenario.name),
                    SberScenarioControlButton(coordinator, scenario.id, scenario.name, "stop"),
                    SberScenarioControlButton(coordinator, scenario.id, scenario.name, "cancel"),
                ]
            )
        if added:
            async_add_entities(added)

    discover_scenarios()
    entry.async_on_unload(coordinator.async_add_listener(discover_scenarios))


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
            ha_entity.unique_id[len(prefix) :] if ha_entity.unique_id.startswith(prefix) else ""
        )
        super().__init__(coordinator, device_id, suffix)
        self._state_key = ha_entity.state_attribute_key or ""
        self._command_value = ha_entity.command_value
        if ha_entity.icon is not None:
            self._attr_icon = ha_entity.icon
        if ha_entity.entity_category is not None:
            self._attr_entity_category = ha_entity.entity_category

    async def async_press(self) -> None:
        await self._async_send_attrs(
            build_button_press_command(
                device_id=self._device_id,
                key=self._state_key,
                command_value=self._command_value,
            )
        )


class _SberScenarioButtonBase(CoordinatorEntity[SberHomeCoordinator], ButtonEntity):
    """Shared scenario identity, availability and service-device grouping."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:script-text-play-outline"

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        scenario_id: str,
        scenario_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._scenario_id = scenario_id
        self._attr_unique_id = f"sberhome_scenario_{scenario_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        scenario = next((s for s in self.coordinator.scenarios if s.id == self._scenario_id), None)
        if scenario is not None and scenario.name:
            if self.translation_key:
                placeholders = {"name": scenario.name}
                if self.translation_placeholders != placeholders:
                    self._attr_translation_placeholders = placeholders
                    # HA caches the substituted name separately from its placeholders.
                    self.__dict__.pop("name", None)
            else:
                self._attr_name = scenario.name
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        # Облако не отвечает или сценария больше нет в списке — недоступен.
        return super().available and any(
            s.id == self._scenario_id for s in self.coordinator.scenarios
        )


class SberScenarioButton(_SberScenarioButtonBase):
    """Existing run entity; its name and unique_id remain unchanged."""

    def __init__(
        self, coordinator: SberHomeCoordinator, scenario_id: str, scenario_name: str
    ) -> None:
        super().__init__(coordinator, scenario_id, scenario_name)
        self._attr_name = scenario_name

    async def async_press(self) -> None:
        async with async_translate_cloud_errors(self.coordinator, refresh_scenarios=True):
            await self.coordinator.async_execute_scenario(self._scenario_id)


class SberScenarioControlButton(_SberScenarioButtonBase):
    """Stop/cancel one scenario without conflating execution with trigger enablement."""

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        scenario_id: str,
        scenario_name: str,
        operation: Literal["stop", "cancel"],
    ) -> None:
        super().__init__(coordinator, scenario_id, scenario_name)
        self._operation = operation
        self._attr_unique_id = f"sberhome_scenario_{operation}_{scenario_id}"
        self._attr_translation_key = f"scenario_{operation}"
        self._attr_translation_placeholders = {"name": scenario_name}
        self._attr_icon = (
            "mdi:stop-circle-outline" if operation == "stop" else "mdi:calendar-remove"
        )

    async def async_press(self) -> None:
        async with async_translate_cloud_errors(self.coordinator, refresh_scenarios=True):
            if self._operation == "stop":
                await self.coordinator.async_stop_scenario(self._scenario_id)
            else:
                try:
                    await self.coordinator.async_cancel_scenario(self._scenario_id)
                except ApiError as err:
                    if err.status_code != 409:
                        raise
                    raise ServiceValidationError(
                        translation_domain=DOMAIN, translation_key="scenario_cancel_not_allowed"
                    ) from err
