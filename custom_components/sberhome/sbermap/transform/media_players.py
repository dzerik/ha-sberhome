"""Media players (TV) — bidirectional sbermap helpers (PR #9)."""

from __future__ import annotations

from typing import Final

from ..values import SberState, SberStateBundle, SberValue

# Sber TV использует фиксированный набор источников.
TV_SOURCES: Final[tuple[str, ...]] = (
    "hdmi1", "hdmi2", "hdmi3", "tv", "av", "content",
)


def build_tv_on_off_command(*, device_id: str, is_on: bool) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("on_off", SberValue.of_bool(is_on)),),
    )


def build_tv_volume_command(
    *, device_id: str, volume_level: float
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("volume_int", SberValue.of_int(int(volume_level * 100))),),
    )


def build_tv_volume_step_command(
    *, device_id: str, direction: str
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("direction", SberValue.of_enum(direction)),),
    )


def build_tv_mute_command(*, device_id: str, mute: bool) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("mute", SberValue.of_bool(mute)),),
    )


def build_tv_source_command(*, device_id: str, source: str) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("source", SberValue.of_enum(source)),),
    )


def build_tv_custom_key_command(*, device_id: str, key: str) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("custom_key", SberValue.of_enum(key)),),
    )


def build_tv_direction_command(
    *, device_id: str, direction: str
) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("direction", SberValue.of_enum(direction)),),
    )


def build_tv_channel_command(*, device_id: str, channel: int) -> SberStateBundle:
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("channel_int", SberValue.of_int(int(channel))),),
    )


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
