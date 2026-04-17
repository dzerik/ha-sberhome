"""Support for SberHome robot vacuums — sbermap-driven (PR #7 + PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.vacuum import (
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import HaEntityData, build_vacuum_command


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberSbermapVacuum] = []
    for device_id, ha_entities in coordinator.entities.items():
        for ent in ha_entities:
            if ent.platform is Platform.VACUUM:
                entities.append(SberSbermapVacuum(coordinator, device_id, ent))
    async_add_entities(entities)


class SberSbermapVacuum(SberBaseEntity, StateVacuumEntity):
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
        ha_entity: HaEntityData,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._ha_unique_id = ha_entity.unique_id

    def _ent(self) -> HaEntityData | None:
        return self._entity_data(self._ha_unique_id)

    @property
    def activity(self) -> VacuumActivity | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.state if isinstance(ent.state, VacuumActivity) else None

    @property
    def battery_level(self) -> int | None:
        ent = self._ent()
        if ent is None:
            return None
        return ent.attributes.get("battery_level")

    async def async_start(self) -> None:
        await self._async_send_attrs(
            build_vacuum_command(device_id=self._device_id, command="start")
        )

    async def async_pause(self) -> None:
        await self._async_send_attrs(
            build_vacuum_command(device_id=self._device_id, command="pause")
        )

    async def async_stop(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_vacuum_command(device_id=self._device_id, command="stop")
        )

    async def async_return_to_base(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_vacuum_command(
                device_id=self._device_id, command="return_to_base"
            )
        )

    async def async_locate(self, **kwargs: Any) -> None:
        await self._async_send_attrs(
            build_vacuum_command(device_id=self._device_id, command="locate")
        )
