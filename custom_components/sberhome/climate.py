"""Support for SberHome HVAC (AC, heater, radiator, boiler, underfloor)."""

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
from .registry import CATEGORY_CLIMATE, ClimateSpec, resolve_category

# Sber → HA HVAC mode mapping.
# Sber может прислать как "fan_only" так и "fan" — оба маппим в HVACMode.FAN_ONLY.
SBER_TO_HA_HVAC: dict[str, HVACMode] = {
    "auto": HVACMode.AUTO,
    "cool": HVACMode.COOL,
    "heat": HVACMode.HEAT,
    "dry": HVACMode.DRY,
    "fan_only": HVACMode.FAN_ONLY,
    "fan": HVACMode.FAN_ONLY,
}
# Обратный маппинг — явный, чтобы не зависеть от порядка итерации dict
# (HVACMode.FAN_ONLY → "fan_only", каноничное значение из sber spec).
HA_TO_SBER_HVAC: dict[HVACMode, str] = {
    HVACMode.AUTO: "auto",
    HVACMode.COOL: "cool",
    HVACMode.HEAT: "heat",
    HVACMode.DRY: "dry",
    HVACMode.FAN_ONLY: "fan_only",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SberGenericClimate] = []
    for device_id, device in coordinator.data.items():
        category = resolve_category(device)
        if category is None:
            continue
        spec = CATEGORY_CLIMATE.get(category)
        if spec is not None:
            entities.append(SberGenericClimate(coordinator, device_id, spec))
    async_add_entities(entities)


class SberGenericClimate(SberBaseEntity, ClimateEntity):
    """Универсальное HVAC-устройство."""

    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        device_id: str,
        spec: ClimateSpec,
    ) -> None:
        super().__init__(coordinator, device_id)
        self._spec = spec
        self._attr_min_temp = spec.min_temp
        self._attr_max_temp = spec.max_temp
        self._attr_target_temperature_step = spec.step

        features = ClimateEntityFeature(0)
        if spec.temperature_key:
            features |= ClimateEntityFeature.TARGET_TEMPERATURE
        if spec.fan_mode_key and spec.fan_modes:
            features |= ClimateEntityFeature.FAN_MODE
            self._attr_fan_modes = list(spec.fan_modes)
        features |= ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        self._attr_supported_features = features

        # HVAC modes: всегда есть OFF; если есть список — добавляем все HA-эквиваленты.
        modes: list[HVACMode] = [HVACMode.OFF]
        for m in spec.hvac_modes:
            ha = SBER_TO_HA_HVAC.get(m)
            if ha and ha not in modes:
                modes.append(ha)
        if len(modes) == 1:
            # Без списка режимов — считаем это heater
            modes.append(HVACMode.HEAT)
        self._attr_hvac_modes = modes

    # ---- on/off + mode ----
    @property
    def hvac_mode(self) -> HVACMode:
        on_state = self._get_desired_state("on_off")
        if not on_state or not on_state.get("bool_value"):
            return HVACMode.OFF
        if self._spec.hvac_modes_key:
            state = self._get_desired_state(self._spec.hvac_modes_key)
            if state and "enum_value" in state:
                return SBER_TO_HA_HVAC.get(state["enum_value"], HVACMode.AUTO)
        return HVACMode.HEAT

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self._async_send_states([{"key": "on_off", "bool_value": False}])
            return
        states: list[dict] = [{"key": "on_off", "bool_value": True}]
        if self._spec.hvac_modes_key and hvac_mode in HA_TO_SBER_HVAC:
            states.append(
                {
                    "key": self._spec.hvac_modes_key,
                    "enum_value": HA_TO_SBER_HVAC[hvac_mode],
                }
            )
        await self._async_send_states(states)

    # ---- temperature ----
    @property
    def target_temperature(self) -> float | None:
        if not self._spec.temperature_key:
            return None
        state = self._get_desired_state(self._spec.temperature_key)
        if state:
            if "integer_value" in state:
                return float(state["integer_value"])
            if "float_value" in state:
                return state["float_value"]
        return None

    @property
    def current_temperature(self) -> float | None:
        if not self._spec.current_temp_key:
            return None
        state = self._get_reported_state(self._spec.current_temp_key)
        if state:
            if "float_value" in state:
                return state["float_value"]
            if "integer_value" in state:
                return float(state["integer_value"])
        return None

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is None or not self._spec.temperature_key:
            return
        await self._async_send_states(
            [{"key": self._spec.temperature_key, "integer_value": int(temp)}]
        )

    # ---- fan ----
    @property
    def fan_mode(self) -> str | None:
        if not self._spec.fan_mode_key:
            return None
        state = self._get_desired_state(self._spec.fan_mode_key)
        return state["enum_value"] if state and "enum_value" in state else None

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        if not self._spec.fan_mode_key:
            return
        await self._async_send_states(
            [{"key": self._spec.fan_mode_key, "enum_value": fan_mode}]
        )

    # ---- on/off ----
    async def async_turn_on(self) -> None:
        await self._async_send_states([{"key": "on_off", "bool_value": True}])

    async def async_turn_off(self) -> None:
        await self._async_send_states([{"key": "on_off", "bool_value": False}])
