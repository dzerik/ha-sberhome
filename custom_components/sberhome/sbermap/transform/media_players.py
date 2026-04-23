"""Media players (TV) — command builders."""

from __future__ import annotations

from typing import Final

from ...aiosber.dto import AttributeValueDto

TV_SOURCES: Final[tuple[str, ...]] = (
    "hdmi1",
    "hdmi2",
    "hdmi3",
    "tv",
    "av",
    "content",
)


def build_tv_on_off_command(*, device_id: str, is_on: bool) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_bool("on_off", is_on)]


def build_tv_volume_command(*, device_id: str, volume_level: float) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_int("volume_int", int(volume_level * 100))]


def build_tv_volume_step_command(*, device_id: str, direction: str) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum("direction", direction)]


def build_tv_mute_command(*, device_id: str, mute: bool) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_bool("mute", mute)]


def build_tv_source_command(*, device_id: str, source: str) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum("source", source)]


def build_tv_custom_key_command(*, device_id: str, key: str) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum("custom_key", key)]


def build_tv_direction_command(*, device_id: str, direction: str) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum("direction", direction)]


def build_tv_channel_command(*, device_id: str, channel: int) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_int("channel_int", int(channel))]


__all__ = [
    "TV_SOURCES",
    "build_tv_channel_command",
    "build_tv_custom_key_command",
    "build_tv_direction_command",
    "build_tv_mute_command",
    "build_tv_on_off_command",
    "build_tv_source_command",
    "build_tv_volume_command",
    "build_tv_volume_step_command",
]
