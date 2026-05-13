"""Pure matcher: ListenerSpec × EventMeta → bool."""

from __future__ import annotations

from dataclasses import dataclass

from .spec import ListenerSpec


@dataclass(frozen=True, slots=True)
class EventMeta:
    """Минимальный snapshot Sber scenario event'а для matching.

    Заполняется в ``coordinator._fire_intent_event`` из ``ScenarioEventDto``
    + ``_extract_trigger_type``. Чистая структура — никаких ссылок на
    coordinator/HA/DTO.

    Все поля optional — Sber иногда отдаёт неполный payload.
    """

    scenario_id: str | None
    scenario_name: str | None
    trigger_type: str | None
    home_id: str | None


def _normalize(s: str | None) -> str | None:
    """Strip + casefold для case/whitespace-tolerant сравнения."""
    return s.strip().casefold() if s is not None else None


def match_listener(spec: ListenerSpec, event: EventMeta) -> bool:
    """True если listener matches event (AND across non-None filter fields).

    Disabled listeners всегда False. Filter field == None означает «любой».
    """
    if not spec.enabled:
        return False

    f = spec.filter

    if f.trigger_types is not None and (
        event.trigger_type is None or event.trigger_type not in f.trigger_types
    ):
        return False

    if f.scenario_name is not None and _normalize(f.scenario_name) != _normalize(
        event.scenario_name
    ):
        return False

    if f.scenario_id is not None and f.scenario_id != event.scenario_id:
        return False

    return not (f.home_id is not None and f.home_id != event.home_id)
