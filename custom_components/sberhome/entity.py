"""Base entity for SberHome integration — fully DTO-driven."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aiosber.dto import AttributeValueDto
from .const import DOMAIN, LOGGER
from .coordinator import SberHomeCoordinator
from .exceptions import SberAuthError

if TYPE_CHECKING:
    from .aiosber.dto.device import DeviceDto
    from .sbermap import HaEntityData


class SberBaseEntity(CoordinatorEntity[SberHomeCoordinator]):
    """Base class for all SberHome entities (DTO-driven)."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        unique_id_suffix: str = "",
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        dto = coordinator.devices.get(device_id)
        device_real_id = (dto.id if dto else None) or device_id
        self._attr_unique_id = (
            f"{device_real_id}_{unique_id_suffix}" if unique_id_suffix else device_real_id
        )
        if unique_id_suffix:
            self._attr_name = unique_id_suffix.replace("_", " ").title()
            self._attr_translation_key = unique_id_suffix
        else:
            self._attr_name = None

    @property
    def available(self) -> bool:
        """Available ≡ coordinator live + device в state_cache + online=True.

        Sber API даёт online-флаг в reported_state, key="online", type=BOOL.
        Отсутствует он — считаем available (legacy-устройства). Ложью он
        бывает редко и только для battery-powered sensors с sleep-mode.
        """
        if not super().available:
            return False
        dto = self.coordinator.state_cache.get_device(self._device_id)
        if dto is None:
            return False
        for av in dto.reported_state:
            if av.key == "online":
                # BOOL API value. av.value type-aware возвращает bool_value.
                online = av.value
                if isinstance(online, bool):
                    return online
                break
        return True

    @property
    def _device_dto(self) -> DeviceDto | None:
        """Типизированный DTO из StateCache."""
        return self.coordinator.state_cache.get_device(self._device_id)

    def _entity_data(self, unique_id: str) -> HaEntityData | None:
        """Найти HaEntityData по unique_id в coordinator.entities[device_id]."""
        for ent in self.coordinator.entities.get(self._device_id, []):
            if ent.unique_id == unique_id:
                return ent
        return None

    @property
    def device_info(self) -> DeviceInfo:
        dto = self._device_dto
        serial = (
            (dto.serial_number if dto else None) or (dto.id if dto else None) or self._device_id
        )
        name = dto.display_name if dto else None
        model = dto.device_info.model if dto and dto.device_info else None
        sw_version = dto.sw_version if dto else None
        room_name = self.coordinator.state_cache.device_room(self._device_id)
        return DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=name,
            manufacturer="Sber",
            model=model,
            sw_version=sw_version,
            serial_number=serial,
            suggested_area=room_name,
        )

    async def _async_send_attrs(self, attrs: list[AttributeValueDto]) -> None:
        """Send list[AttributeValueDto] via API + optimistic cache update."""
        states_dicts = [a.to_dict() for a in attrs]
        try:
            await self.coordinator.home_api.set_device_state(self._device_id, states_dicts)
        except SberAuthError as err:
            LOGGER.warning("Auth failed on command, triggering reauth: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err

        # Логируем исходящую команду в WS ring buffer — пользователь видит
        # свои команды рядом с входящими push'ами в панели логов.
        self.coordinator.record_command(self._device_id, states_dicts)
        # DevTools #4: запоминаем команду в confirmation-tracker.  На
        # следующем reported_state для этого device tracker сверит какие
        # keys подтвердились — Sber протокол не даёт correlation id, так
        # что watch-and-match это единственный способ поймать silent
        # rejection (HTTP 200, но device ничего не применил).
        try:
            self.coordinator.command_tracker.record_sent(self._device_id, states_dicts)
        except Exception:  # pragma: no cover — DevTools must never break sending
            LOGGER.exception("CommandTracker.record_sent failed")

        # Optimistic patch: применяем desired state к локальному кэшу,
        # пересобираем entities и уведомляем подписчиков. Публичный hook —
        # без лазания в приватный `_rebuild_dto_caches` и передачи stale
        # `coordinator.data` (эту проблему отмечал аудит P1 #15).
        self.coordinator.state_cache.patch_device_desired(self._device_id, attrs)
        self.coordinator.rebuild_caches_and_notify()

    async def _async_send_command(self, **features: Any) -> None:
        """Send command via bidirectional mapper.

        Usage: ``await self._async_send_command(on_off=True, light_brightness=200)``
        """
        from .sbermap import build_command

        await self._async_send_attrs(build_command(self._device_id, **features))
