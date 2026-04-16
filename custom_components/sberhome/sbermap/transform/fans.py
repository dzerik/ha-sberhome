"""Fans — bidirectional sbermap helpers (PR #9)."""

from __future__ import annotations

from ..values import SberState, SberStateBundle, SberValue


def build_fan_turn_on_command(
    *, device_id: str, preset_mode: str | None = None
) -> SberStateBundle:
    states: list[SberState] = [SberState("on_off", SberValue.of_bool(True))]
    if preset_mode:
        states.append(
            SberState("hvac_air_flow_power", SberValue.of_enum(preset_mode))
        )
    return SberStateBundle(device_id=device_id, states=tuple(states))


def build_fan_turn_off_command(*, device_id: str) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("on_off", SberValue.of_bool(False)),),
    )


def build_fan_preset_command(
    *, device_id: str, preset_mode: str
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("hvac_air_flow_power", SberValue.of_enum(preset_mode)),),
    )


__all__ = [
    "build_fan_preset_command",
    "build_fan_turn_off_command",
    "build_fan_turn_on_command",
]
