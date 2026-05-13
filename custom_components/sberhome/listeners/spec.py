"""Dataclass-спеки для listeners (read-only маппинг Sber events → HA events)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ListenerFilter:
    """Фильтр для match'а Sber scenario event.

    Все поля optional; ``yaml_loader`` гарантирует что минимум одно
    поле задано (пустой filter — анти-паттерн «matches everything»).
    Matcher AND-объединяет все non-None поля.

    Attributes:
        trigger_types: набор enum-значений из ``start_scenario_reason.type``
            (PHRASES/TIME/DEVICE/GEO_TIME/CONDITIONS/CHECK_DEVICE/
            CHECK_SCENARIO/UNDEFINED_TYPE). ``None`` означает «любой».
        scenario_name: точное имя Sber-сценария (нормализуется через
            strip + casefold перед сравнением).
        scenario_id: UUID Sber-сценария — exact match.
        home_id: UUID дома — exact match. Резолвится из YAML
            ``home``/``home_id`` в reconcile-time (когда state_cache готов).
    """

    trigger_types: frozenset[str] | None = None
    scenario_name: str | None = None
    scenario_id: str | None = None
    home_id: str | None = None


@dataclass(slots=True)
class ListenerSpec:
    """Один listener — единица YAML-декларации.

    Attributes:
        slug: уникальный machine-handle (event_data.slug в HA event).
        name: display name для UI.
        filter: фильтрационная семантика.
        enabled: если False — `match_listener` всегда возвращает False.
        description: optional пользовательское описание (показывается в UI).
        last_fired_at: in-memory timestamp последнего match'а (ISO-8601).
            Сбрасывается при reload/restart. Не персистится.
    """

    slug: str
    name: str
    filter: ListenerFilter = field(default_factory=ListenerFilter)
    enabled: bool = True
    description: str = ""
    last_fired_at: str | None = None
