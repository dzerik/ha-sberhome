"""Buttons — command builder."""

from __future__ import annotations

from ...aiosber.dto import AttributeValueDto


def build_button_press_command(
    *,
    device_id: str,
    key: str,
    command_value: str | None = None,
) -> list[AttributeValueDto]:
    """Build single-action command."""
    if command_value is not None:
        return [AttributeValueDto.of_enum(key, command_value)]
    return [AttributeValueDto.of_bool(key, True)]


__all__ = ["build_button_press_command"]
