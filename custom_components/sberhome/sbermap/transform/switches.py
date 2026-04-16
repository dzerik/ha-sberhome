"""Switches — bidirectional sbermap helpers (PR #9).

Generic switch builder. Используется для primary on_off (`socket`/`relay`/`kettle`)
и для extra-switches (child_lock/night_mode/ionization/aromatization/decontaminate/
alarm_mute) через параметр `state_key`.
"""

from __future__ import annotations

from ..values import SberState, SberStateBundle, SberValue


def build_switch_command(
    *, device_id: str, state_key: str = "on_off", is_on: bool
) -> SberStateBundle:
    """HA switch turn_on/turn_off → SberStateBundle.

    Args:
        device_id: Sber device UUID.
        state_key: Sber feature key (default "on_off"; для extra-switches —
            "child_lock"/"hvac_night_mode"/etc.).
        is_on: target state.
    """
    return SberStateBundle(
        device_id=device_id,
        states=(SberState(state_key, SberValue.of_bool(is_on)),),
    )


__all__ = ["build_switch_command"]
