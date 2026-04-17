"""Climate — state read + command builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ...aiosber.dto import AttributeValueDto

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto


@dataclass(slots=True, frozen=True)
class ClimateConfig:
    """Per-category HVAC configuration."""

    min_temp: float
    max_temp: float
    step: float
    hvac_modes: tuple[str, ...] = ()
    fan_modes: tuple[str, ...] = ()
    has_fan: bool = False
    has_hvac_modes: bool = False
    current_temp_key: str = "temperature"
    target_temp_key: str = "hvac_temp_set"
    fan_mode_key: str = "hvac_air_flow_power"
    hvac_modes_key: str = "hvac_work_mode"


_CONFIGS: dict[str, ClimateConfig] = {
    "hvac_ac": ClimateConfig(
        min_temp=16, max_temp=30, step=1,
        hvac_modes=("auto", "cool", "heat", "dry", "fan_only"),
        fan_modes=("auto", "low", "medium", "high", "turbo"),
        has_fan=True, has_hvac_modes=True,
    ),
    "hvac_heater": ClimateConfig(
        min_temp=7, max_temp=30, step=1,
        fan_modes=("auto", "low", "medium", "high", "turbo"),
        has_fan=True,
    ),
    "hvac_radiator": ClimateConfig(min_temp=25, max_temp=40, step=5),
    "hvac_boiler": ClimateConfig(min_temp=25, max_temp=80, step=5),
    "hvac_underfloor_heating": ClimateConfig(min_temp=25, max_temp=50, step=5),
}


def climate_config_for(category: str) -> ClimateConfig | None:
    return _CONFIGS.get(category)


@dataclass(slots=True, frozen=True)
class ClimateState:
    """Snapshot of HVAC state from DeviceDto."""

    is_on: bool
    hvac_mode: str
    target_temperature: float | None = None
    current_temperature: float | None = None
    fan_mode: str | None = None


def _dto_value(dto: DeviceDto, key: str, *, desired: bool = False) -> Any:
    """Extract value from DTO reported_state (or desired_state)."""
    source = dto.desired_state if desired else dto.reported_state
    for av in source:
        if av.key == key:
            return av.value
    return None


def map_hvac_mode(sber_mode: str | None, *, is_on: bool) -> Any:
    """Sber hvac_work_mode → HA HVACMode."""
    from homeassistant.components.climate import HVACMode

    if not is_on:
        return HVACMode.OFF
    _map: dict[str, Any] = {
        "cool": HVACMode.COOL, "heat": HVACMode.HEAT,
        "dry": HVACMode.DRY, "fan": HVACMode.FAN_ONLY,
        "fan_only": HVACMode.FAN_ONLY, "auto": HVACMode.AUTO,
    }
    return _map.get(str(sber_mode), HVACMode.AUTO) if sber_mode else HVACMode.AUTO


def map_hvac_mode_to_sber(ha_mode: Any) -> str | None:
    """HA HVACMode → Sber wire value. None for OFF."""
    from homeassistant.components.climate import HVACMode

    if ha_mode is None or ha_mode == HVACMode.OFF:
        return None
    _map: dict[Any, str] = {
        HVACMode.AUTO: "auto", HVACMode.COOL: "cool",
        HVACMode.HEAT: "heat", HVACMode.DRY: "dry",
        HVACMode.FAN_ONLY: "fan_only",
    }
    return _map.get(ha_mode, str(ha_mode))


def climate_state_from_dto(dto: DeviceDto, config: ClimateConfig) -> ClimateState:
    """Read HVAC state from DeviceDto."""
    is_on_raw = _dto_value(dto, "on_off", desired=True)
    is_on = bool(is_on_raw) if is_on_raw is not None else False
    target = _dto_value(dto, config.target_temp_key, desired=True)
    current = _dto_value(dto, config.current_temp_key)
    fan = _dto_value(dto, config.fan_mode_key, desired=True)
    raw_mode = _dto_value(dto, config.hvac_modes_key, desired=True)
    return ClimateState(
        is_on=is_on,
        hvac_mode=map_hvac_mode(raw_mode, is_on=is_on),
        target_temperature=float(target) if target is not None else None,
        current_temperature=float(current) if current is not None else None,
        fan_mode=str(fan) if fan is not None else None,
    )


# ============================================================================
# Command builders
# ============================================================================
def build_climate_set_hvac_mode_command(
    *, device_id: str, hvac_mode: Any, config: ClimateConfig
) -> list[AttributeValueDto]:
    from homeassistant.components.climate import HVACMode

    attrs: list[AttributeValueDto] = []
    if hvac_mode == HVACMode.OFF:
        attrs.append(AttributeValueDto.of_bool("on_off", False))
    else:
        attrs.append(AttributeValueDto.of_bool("on_off", True))
        sber_mode = map_hvac_mode_to_sber(hvac_mode)
        if sber_mode is not None and config.has_hvac_modes:
            attrs.append(AttributeValueDto.of_enum(config.hvac_modes_key, sber_mode))
    return attrs


def build_climate_set_temperature_command(
    *, device_id: str, temperature: float, config: ClimateConfig
) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_int(config.target_temp_key, int(temperature))]


def build_climate_set_fan_mode_command(
    *, device_id: str, fan_mode: str, config: ClimateConfig
) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum(config.fan_mode_key, fan_mode)]


def build_climate_on_off_command(
    *, device_id: str, is_on: bool
) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_bool("on_off", is_on)]


__all__ = [
    "ClimateConfig",
    "ClimateState",
    "build_climate_on_off_command",
    "build_climate_set_fan_mode_command",
    "build_climate_set_hvac_mode_command",
    "build_climate_set_temperature_command",
    "climate_config_for",
    "climate_state_from_dto",
    "map_hvac_mode",
    "map_hvac_mode_to_sber",
]
