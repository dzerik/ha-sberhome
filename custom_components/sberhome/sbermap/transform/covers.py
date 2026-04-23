"""Covers — state read + command builders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.cover import CoverState

from ...aiosber.dto import AttributeValueDto

if TYPE_CHECKING:
    from ...aiosber.dto.device import DeviceDto


@dataclass(slots=True, frozen=True)
class CoverConfig:
    """Per-category cover features."""

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
    """Snapshot of cover state from DeviceDto."""

    state: str
    current_position: int | None


def cover_state_from_dto(dto: DeviceDto) -> CoverStateSnapshot:
    raw_state = str(dto.reported_value("open_state") or "closed")
    state = _OPEN_STATE_MAP.get(raw_state, CoverState.CLOSED)
    pos_raw = dto.reported_value("open_percentage")
    return CoverStateSnapshot(
        state=state,
        current_position=int(pos_raw) if pos_raw is not None else None,
    )


def build_cover_position_command(*, device_id: str, position: int) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_int("open_set", int(position))]


def build_cover_stop_command(*, device_id: str) -> list[AttributeValueDto]:
    return [AttributeValueDto.of_enum("open_state", "stop")]


__all__ = [
    "CoverConfig",
    "CoverStateSnapshot",
    "build_cover_position_command",
    "build_cover_stop_command",
    "cover_config_for",
    "cover_state_from_dto",
]
