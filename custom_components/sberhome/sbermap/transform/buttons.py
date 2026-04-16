"""Buttons — bidirectional sbermap helpers (PR #9).

Fire-and-forget action button (intercom unlock/reject_call).
"""

from __future__ import annotations

from ..values import SberState, SberStateBundle, SberValue


def build_button_press_command(
    *,
    device_id: str,
    key: str,
    command_value: str | None = None,
) -> SberStateBundle:
    """Build single-action command bundle.

    Если `command_value` задан — отправляет enum_value, иначе bool_value=True.
    """
    if command_value is not None:
        value = SberValue.of_enum(command_value)
    else:
        value = SberValue.of_bool(True)
    return SberStateBundle(
        device_id=device_id,
        states=(SberState(key, value),),
    )


__all__ = ["build_button_press_command"]
