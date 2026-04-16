"""Vacuums — bidirectional sbermap helpers (PR #9).

Vacuum status mapping → re-export из sber_to_ha (`map_vacuum_status`).
Команды: start/pause/stop/return_to_base/locate.
"""

from __future__ import annotations

from typing import Literal

from ..values import SberState, SberStateBundle, SberValue
from .sber_to_ha import map_vacuum_status

VacuumCommand = Literal["start", "pause", "stop", "return_to_base", "locate"]


def build_vacuum_command(
    *, device_id: str, command: VacuumCommand
) -> SberStateBundle:
    """Vacuum command → bundle с key=vacuum_cleaner_command, enum_value=command."""
    return SberStateBundle(
        device_id=device_id,
        states=(
            SberState("vacuum_cleaner_command", SberValue.of_enum(command)),
        ),
    )


__all__ = ["VacuumCommand", "build_vacuum_command", "map_vacuum_status"]
