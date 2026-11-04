"""Lossless TIME conditions and the deliberately small schedule editor contract."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .spec import IntentTrigger

DAYS = ("MO", "TU", "WE", "TH", "FR", "SA", "SU")
_RULE = re.compile(
    r"DTSTART;TZID=([A-Za-z0-9_+/-]+):(\d{8}T\d{6})\n"
    r"RRULE:FREQ=DAILY;WKST=MO;BYDAY=([A-Z,]+);"
    r"BYHOUR=(\d{1,2});BYMINUTE=(\d{1,2});BYSECOND=0"
)


class ScheduleError(ValueError):
    """A newly entered schedule is incomplete or unsupported."""

    translation_key = "scenario_schedule_invalid"


class ReadOnlyScheduleError(ScheduleError):
    """An opaque schedule or its anchor cannot be rewritten by the simple editor."""

    translation_key = "scenario_schedule_read_only"


@dataclass(frozen=True, slots=True)
class Schedule:
    """An editable daily rule, with its original start and zone."""

    timezone: str
    start: str
    days: tuple[str, ...]
    hour: int
    minute: int


def parse_schedule(rrule: Any, timezone: Any = None) -> Schedule | None:
    """Recognize only the canonical form; parsing is never a lossy fallback."""
    if not isinstance(rrule, str) or (match := _RULE.fullmatch(rrule)) is None:
        return None
    zone, start, byday, hour_text, minute_text = match.groups()
    days = tuple(byday.split(","))
    hour, minute = int(hour_text), int(minute_text)
    if (
        (timezone is not None and timezone != zone)
        or len(set(days)) != len(days)
        or any(day not in DAYS for day in days)
        or hour > 23
        or minute > 59
    ):
        return None
    try:
        ZoneInfo(zone)
        datetime.strptime(start, "%Y%m%dT%H%M%S")
    except (ValueError, ZoneInfoNotFoundError):
        return None
    return Schedule(zone, start, days, hour, minute)


def editable_time(raw: dict[str, Any], timezone: Any = None) -> Schedule | None:
    """Non-null unknown fields or execute_at make the whole TIME opaque."""
    data = raw.get("time_data")
    if (
        raw.get("type") != "TIME"
        or any(v is not None for k, v in raw.items() if k not in ("type", "time_data"))
        or not isinstance(data, dict)
        or set(data) - {"rrule", "execute_at"}
        or data.get("execute_at") is not None
    ):
        return None
    return parse_schedule(data.get("rrule"), timezone)


def decode_time(raw: dict[str, Any]) -> IntentTrigger:
    """Keep missing/null/types and the entire original condition, not just rrule."""
    data = {"_raw": deepcopy(raw)}
    time_data = raw.get("time_data")
    if isinstance(time_data, dict) and "rrule" in time_data:
        data["rrule"] = deepcopy(time_data["rrule"])
    return IntentTrigger(type="time", data=data)


def encode_time(trigger: IntentTrigger, timezone: Any = None) -> dict[str, Any]:
    """Pass untouched originals through; validate every deliberate schedule edit."""
    data = trigger.data
    if "_raw" in data:
        raw = data["_raw"]
        if not isinstance(raw, dict) or raw.get("type") != "TIME":
            raise ScheduleError("Missing original TIME condition")
        previous = raw.get("time_data")
        previous = previous if isinstance(previous, dict) else {}
        same_presence = ("rrule" in data) == ("rrule" in previous)
        if (
            same_presence
            and type(data.get("rrule")) is type(previous.get("rrule"))
            and data.get("rrule") == previous.get("rrule")
        ):
            return deepcopy(raw)
        original = editable_time(raw, timezone)
        if original is None:
            raise ReadOnlyScheduleError("This TIME must be preserved unchanged")
        parsed = parse_schedule(data.get("rrule"), timezone)
        if parsed is None:
            raise ScheduleError("Choose days and a valid local time")
        if (original.start, original.timezone) != (parsed.start, parsed.timezone):
            raise ReadOnlyScheduleError("The start and timezone must remain unchanged")
        result = deepcopy(raw)
        result["time_data"]["rrule"] = data["rrule"]
        return result
    if parse_schedule(data.get("rrule"), timezone) is None:
        raise ScheduleError("Choose days and a valid local time")
    return {"type": "TIME", "time_data": {"execute_at": None, "rrule": data["rrule"]}}
