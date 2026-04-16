"""Canonical Schedule model — codec-agnostic.

Sber wire-формат (gateway):
```
{
  "days": ["monday", "tuesday", ...],
  "events": [{"time": "08:00", "value_type": "FLOAT", "target_value": 22.5}, ...]
}
```
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Weekday(StrEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


@dataclass(slots=True, frozen=True)
class ScheduleEvent:
    """Single scheduled event (e.g. raise temp to 22°C at 08:00).

    `target_value` хранится как float для simplicity — гетерогенные value-types
    (BOOL/INTEGER) тоже сохранятся через cast.
    """

    time: str  # "HH:MM"
    value_type: str  # "BOOL"/"INTEGER"/"FLOAT"
    target_value: float


@dataclass(slots=True, frozen=True)
class ScheduleValue:
    days: tuple[Weekday, ...] = ()
    events: tuple[ScheduleEvent, ...] = field(default_factory=tuple)
