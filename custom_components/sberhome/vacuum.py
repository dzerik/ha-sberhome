"""Support for SberHome robot vacuum cleaners."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .registry import CATEGORY_VACUUMS, VacuumSpec, resolve_category

# Sber status → HA VacuumActivity
SBER_TO_HA_STATE: dict[str, VacuumActivity] = {
    "cleaning": VacuumActivity.CLEANING,
    "running": VacuumActivity.CLEANING,
    "paused": VacuumActivity.PAUSED,
    "returning": VacuumActivity.RETURNING,
    "docked": VacuumActivity.DOCKED,
    "charging": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
    "error": VacuumActivity.ERROR,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberVacuumEntity] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        spec = CATEGORY_VACUUMS.get(category)
        if spec is not None:
            entities.append(SberVacuumEntity(coordinator, device_id, spec))
    async_add_entities(entities)


class SberVacuumEntity(SberBaseEntity, StateVacuumEntity):
    """Sber робот-пылесос."""

    _attr_supported_features = (
        VacuumEntityFeature.START
        | VacuumEntityFeature.PAUSE
        | VacuumEntityFeature.STOP
        | VacuumEntityFeature.RETURN_HOME
        | VacuumEntityFeature.LOCATE
        | VacuumEntityFeature.BATTERY
        | VacuumEntityFeature.STATE
    )

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: VacuumSpec,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._spec = spec

    @property
    def activity(self) -> VacuumActivity | None:
        state = self._get_reported_state(self._spec.status_key)
        if state and "enum_value" in state:
            return SBER_TO_HA_STATE.get(state["enum_value"], VacuumActivity.IDLE)
        return None

    @property
    def battery_level(self) -> int | None:
        state = self._get_reported_state("battery_percentage")
        if state and "integer_value" in state:
            return int(state["integer_value"])
        return None

    async def async_start(self) -> None:
        await self._command("start")

    async def async_pause(self) -> None:
        await self._command("pause")

    async def async_stop(self, **kwargs: Any) -> None:
        await self._command("stop")

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self._command("return_to_base")

    async def async_locate(self, **kwargs: Any) -> None:
        await self._command("locate")

    async def _command(self, command: str) -> None:
        await self._async_send_states(
            [{"key": self._spec.command_key, "enum_value": command}]
        )
