"""Selects — bidirectional sbermap helpers (PR #9)."""

from __future__ import annotations

from ..values import SberState, SberStateBundle, SberValue


def build_select_command(
    *, device_id: str, key: str, option: str
) -> SberStateBundle:
    """Set enum_value для select-сущности."""
    return SberStateBundle(
        device_id=device_id,
        states=(SberState(key, SberValue.of_enum(option)),),
    )


__all__ = ["build_select_command"]
