"""Base entity for SberHome integration."""

from __future__ import annotations

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .utils import find_from_list
from .const import DOMAIN, LOGGER
from .coordinator import SberHomeCoordinator
from .exceptions import SberAuthError


class SberBaseEntity(CoordinatorEntity[SberHomeCoordinator]):
    """Base class for all SberHome entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        unique_id_suffix: str = "",
    ) -> None:
        super().__init__(coordinator)
        self._device_id = device_id
        device = coordinator.data[device_id]
        device_real_id = device.get("id") or device_id
        self._attr_unique_id = (
            f"{device_real_id}_{unique_id_suffix}"
            if unique_id_suffix
            else device_real_id
        )
        # has_entity_name = True: primary entity (без суффикса) наследует имя
        # устройства из device_info. Secondary entities получают человеко-
        # читаемый суффикс (temperature → "Temperature" в UI).
        if unique_id_suffix:
            # Преобразуем snake_case → Title Case для UI.
            self._attr_name = unique_id_suffix.replace("_", " ").title()
            self._attr_translation_key = unique_id_suffix
        else:
            self._attr_name = None

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data

    @property
    def _device_data(self) -> dict:
        return self.coordinator.data[self._device_id]

    @property
    def device_info(self) -> DeviceInfo:
        device = self._device_data
        serial = device.get("serial_number") or device.get("id", self._device_id)
        name_field = device.get("name")
        if isinstance(name_field, dict):
            name = name_field.get("name")
        elif isinstance(name_field, str):
            name = name_field
        else:
            name = None
        info = device.get("device_info") or {}
        return DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=name,
            manufacturer=info.get("manufacturer"),
            model=info.get("model"),
            sw_version=device.get("sw_version"),
            serial_number=serial,
        )

    def _get_desired_state(self, key: str) -> dict | None:
        if "desired_state" not in self._device_data:
            return None
        return find_from_list(self._device_data["desired_state"], key)

    def _get_reported_state(self, key: str) -> dict | None:
        if "reported_state" not in self._device_data:
            return None
        return find_from_list(self._device_data["reported_state"], key)

    def _get_attribute(self, key: str) -> dict | None:
        if "attributes" not in self._device_data:
            return None
        return find_from_list(self._device_data["attributes"], key)

    async def _async_send_states(self, states: list[dict]) -> None:
        """Отправить команду на устройство + optimistic push.

        При SberAuthError пробрасывает ConfigEntryAuthFailed, чтобы
        триггерить reauth flow (optimistic update ранее его терял).
        """
        try:
            await self.coordinator.home_api.set_device_state(
                self._device_id, states
            )
        except SberAuthError as err:
            LOGGER.warning("Auth failed on command, triggering reauth: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err
        self.coordinator.async_set_updated_data(
            self.coordinator.home_api.get_cached_devices()
        )
