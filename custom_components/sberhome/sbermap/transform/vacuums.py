"""Vacuums — command builder."""

from __future__ import annotations

from typing import Literal

from ...aiosber.dto import AttributeValueDto

VacuumCommand = Literal["start", "pause", "stop", "return_to_base", "locate"]


def build_vacuum_command(*, device_id: str, command: VacuumCommand) -> list[AttributeValueDto]:
    """Vacuum command → list with vacuum_cleaner_command enum."""
    return [AttributeValueDto.of_enum("vacuum_cleaner_command", command)]


__all__ = ["VacuumCommand", "build_vacuum_command"]
