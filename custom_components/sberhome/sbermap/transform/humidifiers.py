"""Humidifiers — bidirectional sbermap helpers (PR #9)."""

from __future__ import annotations

from ..values import SberState, SberStateBundle, SberValue


def build_humidifier_on_off_command(
    *, device_id: str, is_on: bool
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("on_off", SberValue.of_bool(is_on)),),
    )


def build_humidifier_set_humidity_command(
    *, device_id: str, humidity: int
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("hvac_humidity_set", SberValue.of_int(int(humidity))),),
    )


def build_humidifier_set_mode_command(
    *, device_id: str, mode: str
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("hvac_air_flow_power", SberValue.of_enum(mode)),),
    )


__all__ = [
    "build_humidifier_on_off_command",
    "build_humidifier_set_humidity_command",
    "build_humidifier_set_mode_command",
]
