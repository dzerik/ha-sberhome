"""Switches — command builder."""

from __future__ import annotations

from ...aiosber.dto import AttributeValueDto


def build_switch_command(
    *, device_id: str, state_key: str = "on_off", is_on: bool
) -> list[AttributeValueDto]:
    """HA switch turn_on/turn_off → list[AttributeValueDto]."""
    return [AttributeValueDto.of_bool(state_key, is_on)]


__all__ = ["build_switch_command"]
