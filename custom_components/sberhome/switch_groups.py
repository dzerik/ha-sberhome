"""SberGroupSwitch — `switch` entity для Sber custom-groups.

Custom-группа Sber (`group_type=GROUP` в state_cache) — это набор
устройств, которым можно отправить bulk-команду через
`PUT /device_groups/{id}/state` (`GroupAPI.set_state`). Sber разъезжает
команду по устройствам серверной стороной.

Эта entity отдаёт пользователю один toggle на всю группу:
- `is_on` = aggregated (True если хоть один device on; None если
  никто из devices не имеет атрибута on_off).
- `async_turn_on/off` → bulk-команда + optimistic patch локальных
  desired_state для каждого device группы.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aiosber.dto import AttributeValueDto, AttrKey
from .const import DOMAIN

if TYPE_CHECKING:
    from .coordinator import SberHomeCoordinator


class SberGroupSwitch(CoordinatorEntity, SwitchEntity):
    """Bulk on/off switch для Sber custom-группы (group_type=GROUP)."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SberHomeCoordinator, group_id: str) -> None:
        super().__init__(coordinator)
        self._group_id = group_id
        self._attr_unique_id = f"sber_group_{group_id}"
        group = coordinator.state_cache.get_all_groups().get(group_id)
        self._attr_name = group.name if group and group.name else f"Sber group {group_id}"

    @property
    def device_info(self) -> dict[str, Any]:
        return {
            "identifiers": {(DOMAIN, f"group:{self._group_id}")},
            "manufacturer": "Sber",
            "model": "Group",
            "name": self._attr_name,
        }

    def _device_ids(self) -> list[str]:
        return self.coordinator.state_cache.get_group_devices(self._group_id)

    @property
    def available(self) -> bool:
        """True если хотя бы один device группы онлайн."""
        cache = self.coordinator.state_cache
        for device_id in self._device_ids():
            dto = cache.get_device(device_id)
            if dto is None:
                continue
            online = dto.reported_value("online")
            if online is True:
                return True
        return False

    @property
    def is_on(self) -> bool | None:
        """Aggregated state.

        True если хоть один device в группе on. False если все on_off devices off.
        None если ни у одного device нет атрибута on_off (HA трактует как unknown).
        """
        cache = self.coordinator.state_cache
        any_on_off_seen = False
        for device_id in self._device_ids():
            dto = cache.get_device(device_id)
            if dto is None:
                continue
            value = dto.reported_value("on_off")
            if value is None:
                continue
            any_on_off_seen = True
            if value is True:
                return True
        return False if any_on_off_seen else None

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._send_bulk(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._send_bulk(False)

    async def _send_bulk(self, on: bool) -> None:
        await self.coordinator.client.groups.set_state(
            self._group_id,
            [AttributeValueDto.of_bool(AttrKey.ON_OFF, on)],
        )
        # Optimistic patch: каждому device группы патчим desired on_off,
        # чтобы UI не дергался ON→OFF→ON во время WS push'ей.
        cache = self.coordinator.state_cache
        attrs = [AttributeValueDto.of_bool(AttrKey.ON_OFF, on)]
        for device_id in self._device_ids():
            # best-effort optimistic — кэш может уже не содержать device
            with contextlib.suppress(Exception):
                cache.patch_device_desired(device_id, attrs)
        self.async_write_ha_state()


__all__ = ["SberGroupSwitch"]
