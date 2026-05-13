"""Reconciler: применяет YAML-intents к Sber через IntentService.

Стратегия — **additive** (v5.2.0):

1. Парсим YAML-список → ``list[IntentSpec]`` со ``yaml_slug``.
2. Запрашиваем все intent'ы из Sber.
3. Делим их на:

   - **HA-managed** (description содержит маркер `slug=<x>`) →
     mapping ``slug → IntentSpec`` для update-detection.
   - **User-created** (без маркера) — не трогаем.

4. Для каждого YAML intent'а:

   - Найден в HA-managed → **UPDATE** (перезатираем согласно YAML).
   - Не найден → **CREATE** с marker'ом в description.

5. HA-managed intent'ы Sber, которых нет в YAML → **НЕ удаляем**
   (additive). Логируем warning, чтобы пользователь видел: «есть
   sirota'й HA-managed intent, удалите вручную из приложения «Салют!»
   если он лишний».

Sync conflict (пользователь редактировал в Sber-app):
    update перезатрёт правки. Это согласовано пользователем при
    проектировании фичи — приоритет YAML как single source of truth.

Все операции бест-эффорт: ошибка в одном intent'е логируется, но
не блокирует обработку остальных. Итоговый отчёт ``ReconcileReport``
показывает что было создано/обновлено/пропущено/упало.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..aiosber.dto.union import UnionDto
from .marker import build_description, parse_slug_from_description
from .spec import IntentSpec

if TYPE_CHECKING:
    from .service import IntentService

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class ReconcileReport:
    """Итог одной reconcile-итерации — для service-response / тестов."""

    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (slug, reason)

    def to_dict(self) -> dict[str, object]:
        return {
            "created": list(self.created),
            "updated": list(self.updated),
            "unchanged": list(self.unchanged),
            "orphans": list(self.orphans),
            "failed": [{"slug": s, "error": e} for s, e in self.failed],
            "total_yaml": len(self.created) + len(self.updated) + len(self.unchanged),
        }

    def summary_line(self) -> str:
        return (
            f"created={len(self.created)} updated={len(self.updated)} "
            f"unchanged={len(self.unchanged)} orphans={len(self.orphans)} "
            f"failed={len(self.failed)}"
        )


def _resolve_home_id(spec: IntentSpec, homes: list[UnionDto]) -> tuple[str | None, str | None]:
    """Резолвим target home_id для YAML intent'а.

    Приоритет:
    1. `raw_extras["yaml_home_id"]` (явно задан) — берётся как есть,
       проверка существования делается на ловкость Sber (он сам отвергнёт
       если id невалидный).
    2. `raw_extras["yaml_home_name"]` — резолв по `home.name` среди
       `homes`. Регистр игнорируется, trailing whitespace тоже.
    3. Иначе — default home: первый в списке (это и есть «Мой дом» для
       большинства аккаунтов; для multi-home — первый по порядку
       state_cache.get_homes()).

    Returns:
        Кортеж `(home_id, warning)`. `warning` ставится если YAML
        просил конкретный дом, который не нашёлся — reconciler
        включит его в `report.failed[slug] = warning`.
    """
    extras = spec.raw_extras

    explicit_id = extras.get("yaml_home_id")
    if explicit_id:
        return str(explicit_id), None

    name_hint = extras.get("yaml_home_name")
    if name_hint:
        needle = name_hint.strip().casefold()
        for home in homes:
            if home.id and home.name and home.name.strip().casefold() == needle:
                return home.id, None
        # Запрошенный дом не найден — это user-config error, не молчим.
        return None, (f"home={name_hint!r} not found among {[h.name for h in homes if h.name]}")

    # Default = первый дом (см. websocket_api/rooms.py: default = homes[0]).
    # Если домов нет совсем (пустой state_cache / тест) — возвращаем
    # None без warning'а: пользователь не просил явный home, и Sber
    # сам подставит default-дом на стороне сервера.
    if homes:
        return homes[0].id, None
    return None, None


def _prepare_for_sber(spec: IntentSpec, slug: str, home_id: str | None) -> IntentSpec:
    """Подготовить YAML-spec для отправки в Sber: подставить description-маркер
    и target home_id.

    Возвращаем новый instance (мутации избегаем — IntentSpec.actions
    содержит references на оригиналы).
    """
    user_desc = spec.description or ""
    return IntentSpec(
        id=spec.id,
        name=spec.name,
        phrases=list(spec.phrases),
        actions=list(spec.actions),
        enabled=spec.enabled,
        description=build_description(slug, user_desc),
        home_id=home_id,
        raw_extras=dict(spec.raw_extras),
    )


def _spec_equivalent(yaml_spec: IntentSpec, sber_spec: IntentSpec) -> bool:
    """Достаточно ли близки YAML и Sber-версии чтобы пропустить update?

    Сравниваем то, что критично для wire: name, phrases (set), enabled
    и action-dispatch (тип + сериализованный data).
    description-маркер не сравниваем — у sber_spec он уже с маркером,
    а у yaml_spec без.

    Reconcile-инвариант: если ничего из критичного не изменилось — не
    делаем лишних HTTP-вызовов. Минимизирует фланкинг логов и нагрузку
    на Sber.
    """
    if yaml_spec.name.strip() != sber_spec.name.strip():
        return False
    if set(yaml_spec.phrases) != set(sber_spec.phrases):
        return False
    if yaml_spec.enabled != sber_spec.enabled:
        return False
    # home_id — None считаем эквивалентным любому (default-home semantics).
    if yaml_spec.home_id and sber_spec.home_id and yaml_spec.home_id != sber_spec.home_id:
        return False
    # Actions: type + data; порядок важен (исполняются последовательно).
    if len(yaml_spec.actions) != len(sber_spec.actions):
        return False
    for a, b in zip(yaml_spec.actions, sber_spec.actions, strict=True):
        if a.type != b.type:
            return False
        if a.data != b.data:
            return False
    return True


async def reconcile_intents(
    service: IntentService,
    yaml_specs: list[IntentSpec],
    homes: list[UnionDto] | None = None,
) -> ReconcileReport:
    """Применить YAML-конфигурацию intents к Sber.

    Args:
        service: уже инициализированный `IntentService` (через
            `coordinator.client.scenarios`).
        yaml_specs: список IntentSpec из ``yaml_loader.load_intents_from_config``
            с ``raw_extras["yaml_slug"]``.
        homes: список домов из state_cache.get_homes() для резолюции
            `yaml_home`/`yaml_home_id`. Если None — все intent'ы пойдут
            без явного home_id (Sber выберет default-дом сам).

    Returns:
        ReconcileReport: детальный отчёт по операциям.
    """
    report = ReconcileReport()
    homes = homes or []

    # 1. Снапшот всех intent'ов из Sber.
    try:
        existing = await service.list_intents()
    except Exception as err:  # noqa: BLE001 — best-effort, не валим integration
        _LOGGER.exception("Reconciler: list_intents failed, aborting")
        for spec in yaml_specs:
            report.failed.append(
                (spec.raw_extras.get("yaml_slug", "?"), f"list_intents failed: {err}")
            )
        return report

    # 2. HA-managed mapping by slug.
    managed_by_slug: dict[str, IntentSpec] = {}
    for sb in existing:
        slug = parse_slug_from_description(sb.description)
        if slug is not None and sb.id is not None:
            managed_by_slug[slug] = sb

    yaml_slugs = {spec.raw_extras.get("yaml_slug", "") for spec in yaml_specs}

    # 3. Для каждого YAML intent: create / update / unchanged.
    for spec in yaml_specs:
        slug = spec.raw_extras.get("yaml_slug")
        if not slug:
            report.failed.append(("?", "yaml_slug missing — loader bug"))
            continue

        home_id, home_warning = _resolve_home_id(spec, homes)
        if home_warning is not None:
            # User указал явный home, который не найден — failed.
            report.failed.append((slug, home_warning))
            _LOGGER.warning(
                "YAML intent slug=%s: %s — пропуск reconcile.",
                slug,
                home_warning,
            )
            continue

        prepared = _prepare_for_sber(spec, slug, home_id)
        existing_spec = managed_by_slug.get(slug)

        try:
            if existing_spec is None:
                # CREATE
                created = await service.create_intent(prepared)
                report.created.append(slug)
                _LOGGER.info(
                    "YAML intent created: slug=%s name=%r id=%s",
                    slug,
                    spec.name,
                    created.id,
                )
            else:
                # UPDATE — но сначала проверим эквивалентность
                if _spec_equivalent(spec, existing_spec):
                    report.unchanged.append(slug)
                    _LOGGER.debug(
                        "YAML intent unchanged: slug=%s (Sber state matches YAML)",
                        slug,
                    )
                    continue

                # Mergим raw_extras: Sber может хранить служебные поля
                # (image, meta, home_id и т.п.), которые decoder бережно
                # сохраняет в raw_extras. Без этого update теряет их.
                prepared_with_extras = IntentSpec(
                    id=existing_spec.id,
                    name=prepared.name,
                    phrases=prepared.phrases,
                    actions=prepared.actions,
                    enabled=prepared.enabled,
                    description=prepared.description,
                    raw_extras={**existing_spec.raw_extras, **prepared.raw_extras},
                )
                await service.update_intent(existing_spec.id, prepared_with_extras)
                report.updated.append(slug)
                _LOGGER.info(
                    "YAML intent updated: slug=%s name=%r id=%s",
                    slug,
                    spec.name,
                    existing_spec.id,
                )
        except Exception as err:  # noqa: BLE001
            report.failed.append((slug, str(err)))
            _LOGGER.exception("YAML intent failed: slug=%s", slug)

    # 4. Orphan'ы — HA-managed без YAML-counterpart (additive: НЕ удаляем).
    for slug, sb in managed_by_slug.items():
        if slug not in yaml_slugs:
            report.orphans.append(slug)
            _LOGGER.warning(
                "YAML reconcile: orphan HA-managed intent slug=%s name=%r "
                "(не в текущей YAML-конфиге). Additive mode — НЕ удаляем. "
                "Чтобы убрать: удалите вручную в приложении «Салют!» либо "
                "верните секцию в configuration.yaml.",
                slug,
                sb.name,
            )

    _LOGGER.info("YAML reconcile summary: %s", report.summary_line())
    return report


__all__ = ["ReconcileReport", "reconcile_intents"]
