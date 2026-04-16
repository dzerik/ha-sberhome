"""Climate — bidirectional sbermap helpers (PR #9).

Per-category HVAC config + state read + command build. Single source of truth
для всех HVAC-устройств (hvac_ac/heater/radiator/boiler/underfloor_heating).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..values import SberState, SberStateBundle, SberValue
from .sber_to_ha import map_hvac_mode, map_hvac_mode_to_sber

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto


@dataclass(slots=True, frozen=True)
class ClimateConfig:
    """Per-category configuration HVAC."""

    min_temp: float
    max_temp: float
    step: float
    hvac_modes: tuple[str, ...] = ()  # Sber wire values (cool/heat/auto/...)
    fan_modes: tuple[str, ...] = ()
    has_fan: bool = False
    has_hvac_modes: bool = False
    current_temp_key: str = "temperature"
    target_temp_key: str = "hvac_temp_set"
    fan_mode_key: str = "hvac_air_flow_power"
    hvac_modes_key: str = "hvac_work_mode"


_CONFIGS: dict[str, ClimateConfig] = {
    "hvac_ac": ClimateConfig(
        min_temp=16,
        max_temp=30,
        step=1,
        hvac_modes=("auto", "cool", "heat", "dry", "fan_only"),
        fan_modes=("auto", "low", "medium", "high", "turbo"),
        has_fan=True,
        has_hvac_modes=True,
    ),
    "hvac_heater": ClimateConfig(
        min_temp=7,
        max_temp=30,
        step=1,
        fan_modes=("auto", "low", "medium", "high", "turbo"),
        has_fan=True,
    ),
    "hvac_radiator": ClimateConfig(min_temp=25, max_temp=40, step=5),
    "hvac_boiler": ClimateConfig(min_temp=25, max_temp=80, step=5),
    "hvac_underfloor_heating": ClimateConfig(
        min_temp=25, max_temp=50, step=5
    ),
}


def climate_config_for(category: str) -> ClimateConfig | None:
    """Return ClimateConfig для Sber-категории или None если не HVAC."""
    return _CONFIGS.get(category)


@dataclass(slots=True, frozen=True)
class ClimateState:
    """Snapshot of HVAC state read from DeviceDto.desired/reported_state."""

    is_on: bool
    hvac_mode: str  # HA HVACMode value (str)
    target_temperature: float | None = None
    current_temperature: float | None = None
    fan_mode: str | None = None


def _av_value(av_list: list, key: str) -> Any:
    """Extract value (any type) from a list of AttributeValueDto by key.
    Resilient к отсутствующему `type`-полю."""
    for av in av_list or []:
        if av.key != key:
            continue
        if av.bool_value is not None:
            return av.bool_value
        if av.integer_value is not None:
            return av.integer_value
        if av.float_value is not None:
            return av.float_value
        if av.enum_value is not None:
            return av.enum_value
    return None


def climate_state_from_dto(
    dto: DeviceDto, config: ClimateConfig
) -> ClimateState:
    """Read HVAC state from DeviceDto with on_off + work_mode mapping."""
    is_on_raw = _av_value(dto.desired_state, "on_off")
    is_on = bool(is_on_raw) if is_on_raw is not None else False
    target = _av_value(dto.desired_state, config.target_temp_key)
    current = _av_value(dto.reported_state, config.current_temp_key)
    fan = _av_value(dto.desired_state, config.fan_mode_key)
    raw_mode = _av_value(dto.desired_state, config.hvac_modes_key)
    return ClimateState(
        is_on=is_on,
        hvac_mode=map_hvac_mode(raw_mode, is_on=is_on),
        target_temperature=float(target) if target is not None else None,
        current_temperature=float(current) if current is not None else None,
        fan_mode=str(fan) if fan is not None else None,
    )


# ============================================================================
# Command builders (HA → Sber)
# ============================================================================
def build_climate_set_hvac_mode_command(
    *, device_id: str, hvac_mode: Any, config: ClimateConfig
) -> SberStateBundle:
    """HA HVACMode → bundle.

    OFF → on_off=False (без work_mode).
    Остальные → on_off=True + hvac_work_mode=<sber wire value> (если категория поддерживает).
    """
    from homeassistant.components.climate import HVACMode

    states: list[SberState] = []
    if hvac_mode == HVACMode.OFF:
        states.append(SberState("on_off", SberValue.of_bool(False)))
    else:
        states.append(SberState("on_off", SberValue.of_bool(True)))
        sber_mode = map_hvac_mode_to_sber(hvac_mode)
        if sber_mode is not None and config.has_hvac_modes:
            states.append(
                SberState(
                    config.hvac_modes_key,
                    SberValue.of_enum(sber_mode),
                )
            )
    return SberStateBundle(device_id=device_id, states=tuple(states))


def build_climate_set_temperature_command(
    *, device_id: str, temperature: float, config: ClimateConfig
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(
            SberState(
                config.target_temp_key,
                SberValue.of_int(int(temperature)),
            ),
        ),
    )


def build_climate_set_fan_mode_command(
    *, device_id: str, fan_mode: str, config: ClimateConfig
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(
            SberState(config.fan_mode_key, SberValue.of_enum(fan_mode)),
        ),
    )


def build_climate_on_off_command(
    *, device_id: str, is_on: bool
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("on_off", SberValue.of_bool(is_on)),),
    )


__all__ = [
    "ClimateConfig",
    "ClimateState",
    "build_climate_on_off_command",
    "build_climate_set_fan_mode_command",
    "build_climate_set_hvac_mode_command",
    "build_climate_set_temperature_command",
    "climate_config_for",
    "climate_state_from_dto",
]
