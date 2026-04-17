"""Numbers — command builder."""

from __future__ import annotations

from ...aiosber.dto import AttributeValueDto


def build_number_command(
    *, device_id: str, key: str, value: float, scale: float = 1.0
) -> list[AttributeValueDto]:
    """Set integer_value для number-сущности."""
    raw = int(value / scale) if scale else int(value)
    return [AttributeValueDto.of_int(key, raw)]


__all__ = ["build_number_command"]
