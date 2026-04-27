"""Support for SberHome buttons — sbermap-driven (PR #7 + PR #9).

Two flavours of button entities:
- `SberSbermapButton` — per-device fire-and-forget actions (intercom unlock,
  reject_call, …) описанные в sbermap CategorySpec.
- `SberScenarioButton` — отдельная entity на каждый Sber-сценарий из
  ScenarioAPI; нажатие триггерит scenarios.execute_command(scenario_id).
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_button_press_command


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
    # Per-scenario buttons — отдельный device-group "scenarios" в HA.
    for scenario in coordinator.scenarios:
        if scenario.id and scenario.name:
            entities.append(SberScenarioButton(coordinator, scenario.id, scenario.name))
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


class SberScenarioButton(CoordinatorEntity[SberHomeCoordinator], ButtonEntity):
    """Press → executes Sber scenario via ScenarioAPI.execute_command.

    Сценарии — это server-side automations внутри Sber, аналог HA
    automations. Для каждого активного сценария создаётся отдельная
    HA button entity, нажатие которой шлёт его id в `/scenario/v2/command`.

    Все entities группируются в один HA Device "Sber Scenarios" чтобы
    не плодить DeviceEntry на каждую кнопку.
    """

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
        self._attr_name = scenario_name
        self._attr_device_info = {
            "identifiers": {(DOMAIN, "scenarios")},
            "name": "Sber Scenarios",
            "manufacturer": "Sberdevices",
            "model": "Cloud Scenarios",
            "entry_type": "service",
        }

    @property
    def available(self) -> bool:
        # Если сценария больше нет в списке — недоступен.
        return any(s.id == self._scenario_id for s in self.coordinator.scenarios)

    async def async_press(self) -> None:
        await self.coordinator.async_execute_scenario(self._scenario_id)
