"""Base entity for SberHome integration — fully DTO-driven."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aiosber.dto import AttributeValueDto, ColorValue
from .const import DOMAIN, LOGGER
from .coordinator import SberHomeCoordinator
from .exceptions import SberAuthError

if TYPE_CHECKING:
    from .aiosber.dto.device import DeviceDto
    from .sbermap import HaEntityData, SberStateBundle


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
        return (
            super().available
            and self.coordinator.state_cache.get_device(self._device_id) is not None
        )

    @property
    def _device_dto(self) -> DeviceDto | None:
        """Типизированный DTO из StateCache."""
        return self.coordinator.state_cache.get_device(self._device_id)

    @property
    def _device_data(self) -> dict:
        """Legacy raw dict — deprecated, для diagnostics."""
        return self.coordinator.data[self._device_id]

    def _entity_data(self, unique_id: str) -> HaEntityData | None:
        """Найти HaEntityData по unique_id в coordinator.entities[device_id]."""
        for ent in self.coordinator.entities.get(self._device_id, []):
            if ent.unique_id == unique_id:
                return ent
        return None

    @property
    def device_info(self) -> DeviceInfo:
        dto = self._device_dto
        if dto is not None:
            serial = dto.serial_number or dto.id or self._device_id
            name = dto.display_name
            model = dto.device_info.model if dto.device_info else None
            sw_version = dto.sw_version
        else:
            # Fallback на raw dict если DTO недоступен.
            device = self.coordinator.data.get(self._device_id, {})
            serial = device.get("serial_number") or device.get("id", self._device_id)
            name_field = device.get("name")
            name = name_field.get("name") if isinstance(name_field, dict) else name_field
            info = device.get("device_info") or {}
            model = info.get("model")
            sw_version = device.get("sw_version")
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

    async def _async_send_bundle(self, bundle: SberStateBundle) -> None:
        """Convert SberStateBundle → list[AttributeValueDto] → send via API."""
        from .sbermap import ValueType

        attrs: list[AttributeValueDto] = []
        for state in bundle.states:
            v = state.value
            if v.type is ValueType.BOOL:
                attrs.append(AttributeValueDto.of_bool(state.key, v.bool_value))
            elif v.type is ValueType.INTEGER:
                attrs.append(AttributeValueDto.of_int(state.key, v.integer_value))
            elif v.type is ValueType.FLOAT:
                attrs.append(AttributeValueDto.of_float(state.key, v.float_value))
            elif v.type is ValueType.STRING:
                attrs.append(AttributeValueDto.of_string(state.key, v.string_value or ""))
            elif v.type is ValueType.ENUM:
                attrs.append(AttributeValueDto.of_enum(state.key, v.enum_value or ""))
            elif v.type is ValueType.COLOR and v.color_value is not None:
                attrs.append(
                    AttributeValueDto.of_color(
                        state.key,
                        ColorValue(
                            hue=v.color_value.hue,
                            saturation=v.color_value.saturation,
                            brightness=v.color_value.brightness,
                        ),
                    )
                )
            else:
                continue

        # Отправляем через legacy API (поддерживает retry + refresh).
        states_dicts = [a.to_dict() for a in attrs]
        try:
            await self.coordinator.home_api.set_device_state(
                self._device_id, states_dicts
            )
        except SberAuthError as err:
            LOGGER.warning("Auth failed on command, triggering reauth: %s", err)
            raise ConfigEntryAuthFailed(str(err)) from err

        # Optimistic update через StateCache (typed, без raw dict mutation).
        self.coordinator.state_cache.patch_device_desired(self._device_id, attrs)
        self.coordinator._rebuild_dto_caches()
        self.coordinator.async_set_updated_data(
            self.coordinator.home_api.get_cached_devices()
        )
