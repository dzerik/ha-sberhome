"""Fans — command builders."""

from __future__ import annotations

from ...aiosber.dto import AttributeValueDto


def build_fan_turn_on_command(
    *, device_id: str, preset_mode: str | None = None
) -> list[AttributeValueDto]:
    attrs = [AttributeValueDto.of_bool("on_off", True)]
    if preset_mode:
        attrs.append(AttributeValueDto.of_enum("hvac_air_flow_power", preset_mode))
    return attrs


def build_fan_turn_off_command(*, device_id: str) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_bool("on_off", False)]


def build_fan_preset_command(*, device_id: str, preset_mode: str) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum("hvac_air_flow_power", preset_mode)]


__all__ = [
    "build_fan_preset_command",
    "build_fan_turn_off_command",
    "build_fan_turn_on_command",
]
