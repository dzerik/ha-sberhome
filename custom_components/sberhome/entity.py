"""Base entity for SberHome integration — sbermap-driven (PR #8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import SberHomeCoordinator
from .exceptions import SberAuthError

if TYPE_CHECKING:
    from .aiosber.dto.device import DeviceDto
    from .sbermap import HaEntityData, SberStateBundle


class SberBaseEntity(CoordinatorEntity[SberHomeCoordinator]):
    """Base class for all SberHome entities (sbermap-driven)."""

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
        if unique_id_suffix:
            self._attr_name = unique_id_suffix.replace("_", " ").title()
            self._attr_translation_key = unique_id_suffix
        else:
            self._attr_name = None

    @property
    def available(self) -> bool:
        return super().available and self._device_id in self.coordinator.data

    @property
    def _device_data(self) -> dict:
        """Legacy raw dict из coordinator.data — для diagnostics и device_info."""
        return self.coordinator.data[self._device_id]

    @property
    def _device_dto(self) -> DeviceDto | None:
        """Типизированный DTO из coordinator.devices."""
        return self.coordinator.devices.get(self._device_id)

    def _entity_data(self, unique_id: str) -> HaEntityData | None:
        """Найти HaEntityData по unique_id в coordinator.entities[device_id]."""
        for ent in self.coordinator.entities.get(self._device_id, []):
            if ent.unique_id == unique_id:
                return ent
        return None

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
        room_name = self.coordinator.state_cache.device_room(self._device_id)
        return DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name=name,
            manufacturer=info.get("manufacturer"),
            model=info.get("model"),
            sw_version=device.get("sw_version"),
            serial_number=serial,
            suggested_area=room_name,
        )

    async def _async_send_bundle(self, bundle: SberStateBundle) -> None:
        """Convert bundle → list[dict] → send via legacy `home_api.set_device_state`."""
        from .sbermap import ValueType

        states: list[dict] = []
        for state in bundle.states:
            v = state.value
            item: dict = {"key": state.key}
            if v.type is ValueType.BOOL:
                item["bool_value"] = v.bool_value
            elif v.type is ValueType.INTEGER:
                item["integer_value"] = v.integer_value
            elif v.type is ValueType.FLOAT:
                item["float_value"] = v.float_value
            elif v.type is ValueType.STRING:
                item["string_value"] = v.string_value
            elif v.type is ValueType.ENUM:
                item["enum_value"] = v.enum_value
            elif v.type is ValueType.COLOR and v.color_value is not None:
                item["color_value"] = {
                    "hue": v.color_value.hue,
                    "saturation": v.color_value.saturation,
                    "brightness": v.color_value.brightness,
                }
            else:
                continue
            states.append(item)
        try:
            await self.coordinator.home_api.set_device_state(
                self._device_id, states
            )
        except SberAuthError as err:
            LOGGER.warning("Auth failed on command, triggering reauth: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err
        self._merge_optimistic(bundle)
        self.coordinator._rebuild_dto_caches()
        self.coordinator.async_set_updated_data(
            self.coordinator.home_api.get_cached_devices()
        )

    def _merge_optimistic(self, bundle: SberStateBundle) -> None:
        """Optimistic-merge bundle в legacy raw cache, чтобы следующий update
        видел применённые desired_state."""
        cache = self.coordinator.home_api.get_cached_devices()
        if self._device_id not in cache:
            return
        device = cache[self._device_id]
        from .sbermap import ValueType

        for state in bundle.states:
            v = state.value
            patch: dict = {"key": state.key}
            if v.type is ValueType.BOOL:
                patch["bool_value"] = v.bool_value
            elif v.type is ValueType.INTEGER:
                patch["integer_value"] = v.integer_value
            elif v.type is ValueType.FLOAT:
                patch["float_value"] = v.float_value
            elif v.type is ValueType.STRING:
                patch["string_value"] = v.string_value
            elif v.type is ValueType.ENUM:
                patch["enum_value"] = v.enum_value
            elif v.type is ValueType.COLOR and v.color_value is not None:
                patch["color_value"] = {
                    "hue": v.color_value.hue,
                    "saturation": v.color_value.saturation,
                    "brightness": v.color_value.brightness,
                }
            else:
                continue
            for attr in device.get("desired_state", []):
                if attr.get("key") == state.key:
                    attr.update(patch)
                    break
            else:
                device.setdefault("desired_state", []).append(patch)
