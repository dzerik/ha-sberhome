"""Selects — command builder."""

from __future__ import annotations

from ...aiosber.dto import AttributeValueDto


def build_select_command(
    *, device_id: str, key: str, option: str
) -> list[AttributeValueDto]:
    """Set enum_value для select-сущности."""
    return [AttributeValueDto.of_enum(key, option)]


__all__ = ["build_select_command"]
