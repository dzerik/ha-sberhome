"""Humidifiers — command builders."""

from __future__ import annotations

from ...aiosber.dto import AttributeValueDto


def build_humidifier_on_off_command(
    *, device_id: str, is_on: bool
) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_bool("on_off", is_on)]


def build_humidifier_set_humidity_command(
    *, device_id: str, humidity: int
) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_int("hvac_humidity_set", int(humidity))]


def build_humidifier_set_mode_command(
    *, device_id: str, mode: str
) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum("hvac_air_flow_power", mode)]


__all__ = [
    "build_humidifier_on_off_command",
    "build_humidifier_set_humidity_command",
    "build_humidifier_set_mode_command",
]
