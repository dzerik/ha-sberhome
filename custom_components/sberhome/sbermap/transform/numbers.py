"""Numbers — bidirectional sbermap helpers (PR #9).

Применяет inverse scale (HA value → Sber raw int) согласно spec'у NumberSpec.
"""

from __future__ import annotations

from ..values import SberState, SberStateBundle, SberValue


def build_number_command(
    *, device_id: str, key: str, value: float, scale: float = 1.0
) -> SberStateBundle:
    """Set integer_value для number-сущности.

    `scale` — коэффициент HA→Sber: для kettle target_temperature scale=1
    (60..100°C → 60..100 raw); для будущих scaled-полей (e.g. 0.001 для
    мА↔А) — divide value by scale.
    """
    raw = int(value / scale) if scale else int(value)
    return SberStateBundle(
        device_id=device_id,
        states=(SberState(key, SberValue.of_int(raw)),),
    )


__all__ = ["build_number_command"]
