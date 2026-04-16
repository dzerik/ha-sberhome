"""Covers — bidirectional sbermap helpers (PR #9).

Per-category cover features + state read + command build.
Платформа `cover.py` использует только эти функции, не строит SberStateBundle сама.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.cover import CoverState

from ..values import SberState, SberStateBundle, SberValue

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto


@dataclass(slots=True, frozen=True)
class CoverConfig:
    """Per-category cover features (set_position, stop поддерживаются)."""

    supports_set_position: bool = True
    supports_stop: bool = True


_COVER_CONFIGS: dict[str, CoverConfig] = {
    "curtain": CoverConfig(),
    "window_blind": CoverConfig(),
    "gate": CoverConfig(),
    "valve": CoverConfig(supports_set_position=False, supports_stop=False),
}


def cover_config_for(category: str) -> CoverConfig:
    return _COVER_CONFIGS.get(category, CoverConfig())


# ----- Sber open_state → HA CoverState -----
_OPEN_STATE_MAP: dict[str, str] = {
    "open": CoverState.OPEN,
    "opened": CoverState.OPEN,
    "close": CoverState.CLOSED,
    "closed": CoverState.CLOSED,
    "opening": CoverState.OPENING,
    "closing": CoverState.CLOSING,
}


@dataclass(slots=True, frozen=True)
class CoverStateSnapshot:
    """Snapshot of cover state read from DeviceDto.reported_state."""

    state: str  # CoverState value
    current_position: int | None


def _av_value(av_list: list, key: str) -> Any:
    for av in av_list or []:
        if av.key == key:
            if av.bool_value is not None:
                return av.bool_value
            if av.integer_value is not None:
                return av.integer_value
            if av.enum_value is not None:
                return av.enum_value
    return None


def cover_state_from_dto(dto: DeviceDto) -> CoverStateSnapshot:
    raw_state = str(_av_value(dto.reported_state, "open_state") or "closed")
    state = _OPEN_STATE_MAP.get(raw_state, CoverState.CLOSED)
    pos_raw = _av_value(dto.reported_state, "open_percentage")
    return CoverStateSnapshot(
        state=state,
        current_position=int(pos_raw) if pos_raw is not None else None,
    )


def build_cover_position_command(
    *, device_id: str, position: int
) -> SberStateBundle:
    """Set position 0..100 (close=0, open=100)."""
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("open_set", SberValue.of_int(int(position))),),
    )


def build_cover_stop_command(*, device_id: str) -> SberStateBundle:
    """Send stop command (через open_state enum)."""
    return SberStateBundle(
        device_id=device_id,
        states=(SberState("open_state", SberValue.of_enum("stop")),),
    )


__all__ = [
    "CoverConfig",
    "CoverStateSnapshot",
    "build_cover_position_command",
    "build_cover_stop_command",
    "cover_config_for",
    "cover_state_from_dto",
]
