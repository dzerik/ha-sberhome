"""Support for SberHome HVAC — sbermap-driven (PR #5 + bidirectional PR #9)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_TEMPERATURE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .entity import SberBaseEntity
from .sbermap import (
    ClimateConfig,
    build_climate_on_off_command,
    build_climate_set_fan_mode_command,
    build_climate_set_hvac_mode_command,
    build_climate_set_temperature_command,
    climate_config_for,
    climate_state_from_dto,
    map_hvac_mode,
    resolve_category,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberClimateEntity] = []
    for device_id, dto in coordinator.devices.items():
        category = resolve_category(dto.image_set_type)
        if category is None:
            continue
        config = climate_config_for(category)
        if config is None:
            continue
        entities.append(SberClimateEntity(coordinator, device_id, config))
    async_add_entities(entities)


class SberClimateEntity(SberBaseEntity, ClimateEntity):
    """Universal HVAC entity — read через sbermap.climate_state_from_dto."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        config: ClimateConfig,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._config = config
        self._attr_min_temp = config.min_temp
        self._attr_max_temp = config.max_temp
        self._attr_target_temperature_step = config.step

        features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        if config.has_fan and config.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = list(config.fan_modes)
        self._attr_supported_features = features

        modes: list[HVACMode] = [HVACMode.OFF]
        for sber in config.hvac_modes:
            ha = map_hvac_mode(sber, is_on=True)
            if ha not in modes:
                modes.append(ha)
        if len(modes) == 1:
            modes.append(HVACMode.HEAT)
        self._attr_hvac_modes = modes

    def _state(self):
        dto = self._device_dto
        if dto is None:
            return None
        return climate_state_from_dto(dto, self._config)

    @property
    def hvac_mode(self) -> HVACMode:
        s = self._state()
        return s.hvac_mode if s else HVACMode.OFF

    @property
    def target_temperature(self) -> float | None:
        s = self._state()
        return s.target_temperature if s else None

    @property
    def current_temperature(self) -> float | None:
        s = self._state()
        return s.current_temperature if s else None

    @property
    def fan_mode(self) -> str | None:
        s = self._state()
        return s.fan_mode if s else None

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self._async_send_attrs(
            build_climate_set_hvac_mode_command(
                device_id=self._device_id,
                hvac_mode=hvac_mode,
                config=self._config,
            )
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None:
            return
        await self._async_send_attrs(
            build_climate_set_temperature_command(
                device_id=self._device_id,
                temperature=temp,
                config=self._config,
            )
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if not self._config.has_fan:
            return
        await self._async_send_attrs(
            build_climate_set_fan_mode_command(
                device_id=self._device_id,
                fan_mode=fan_mode,
                config=self._config,
            )
        )

    async def async_turn_on(self) -> None:
        await self._async_send_attrs(
            build_climate_on_off_command(device_id=self._device_id, is_on=True)
        )

    async def async_turn_off(self) -> None:
        await self._async_send_attrs(
            build_climate_on_off_command(device_id=self._device_id, is_on=False)
        )
