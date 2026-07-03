"""IntentDispatcher — voice-intent dispatch (Phase 10, issue #35 rearchitect).

Sber пушит ``scenario_widgets.UPDATE_WIDGETS`` каждый раз когда какой-либо
сценарий срабатывает (включая голосовые), парами по ~100ms. Payload
минимальный (без scenario_id) — реальные события резолвятся через
event log ``GET /scenario/v2/event``.

Вынесено из ``coordinator.py`` (SOLID-аудит: God Object, ~230 строк
самодостаточной логики). Coordinator делегирует сюда WS push'и и
lifecycle; сам dispatcher знает только hass/client/state_cache/
listener_registry через DI.

Ключевые механизмы (issue #35):
- **Coalesce-flag pattern**: любой request ставит pending; если worker
  не запущен — стартует. Distinct push'ы, приходящие во время dispatch'а,
  никогда не теряются (asyncio.Lock их раньше молча дропал).
- **Cursor per-home как aware datetime** — string-compare разных
  ISO-форматов Sber (`Z` vs `+00:00`, trimmed fraction) даёт неверный
  порядок.
- **Первый push после рестарта** (cursor=None) не фаерит historical
  events — cursor выставляется на now.
- **Dedup по event_id** (парные push'ы + пересечение WS/poller).
- **Safety-net poller** раз в 30 сек — ловит события при молчащем WS.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from .const import (
    DOMAIN,
    EVENT_SOURCE_LISTENER,
    EVENT_SOURCE_SBER_ONLY,
    LOGGER,
)
from .listeners import EventMeta

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .aiosber import SberClient, StateCache
    from .aiosber.dto.scenario import ScenarioEventDto
    from .listeners import ListenerRegistry

# HA Event bus name для voice-intents. Срабатывает на каждый Sber-сценарий
# (любого типа), который выполнился. Payload:
# {scenario_id, name, event_time, type, account_id, ...}.
EVENT_SBERHOME_INTENT = f"{DOMAIN}_intent"

# Limit для GET /scenario/v2/event — берём последние N событий и фильтруем
# уже обработанные. 30 даёт запас на batch-срабатывания; при saturation
# (все N новых) логируется warning (issue #35 bug #3).
INTENT_FETCH_LIMIT = 30

# Сколько последних event_id запоминать для dedup парных Sber WS push'ей
# и пересечения WS-push + periodic poll.
INTENT_DEDUP_HISTORY = 128

# Periodic safety-net poller. Если WS отвалился/reconnect упал или Sber
# event-log лагает больше окна между push'ами — poller гарантирует
# доставку в течение этого интервала (issue #35 bug #6).
INTENT_POLLER_INTERVAL_SEC = 30.0


def parse_event_time(raw: str | None) -> datetime | None:
    """Parse Sber event_time (ISO-8601) в aware datetime.

    Sber отдаёт `event_time` в разных представлениях:
    - `"2026-04-27T12:44:49.430277Z"` (типовое)
    - потенциально с trimmed trailing zeros (Go RFC3339Nano) — `.43Z`
    - потенциально с явным offset — `+00:00`

    String-compare этих форм даёт неверный ordering (issue #35 bug #4).
    Возвращает None если parse не удался — событие трактуется как
    «без времени» и не участвует в фильтре по cursor'у.
    """
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    try:
        return datetime.fromisoformat(normalized)
    except (ValueError, TypeError):
        return None


def extract_trigger_type(event: ScenarioEventDto) -> str | None:
    """Достать тип триггера сценария из ``ScenarioEventDto.data``.

    Sber wire-format (восстановлен из live traffic мобильного приложения
    «Салют!»):

        data: EventExecutionDetailsDto
        ├── scenario_cancel_time: str | None
        └── start_scenario_reason: StartScenarioReasonDto
            ├── type: ScenarioConditionTypeDto (enum)
            │       — UNDEFINED_TYPE / TIME / PHRASES / CONDITIONS /
            │         DEVICE / CHECK_DEVICE / CHECK_SCENARIO / GEO_TIME
            └── time_data: ScenarioConditionTimeDto

    ``PHRASES`` означает голосовую команду, ``TIME`` — расписание,
    ``DEVICE`` — sensor trigger, и т.п.

    Returns:
        Строка enum-значения как пришла от Sber (например ``"PHRASES"``)
        либо ``None`` если поле отсутствует или не парсится.
    """
    if not event.data or not isinstance(event.data, dict):
        return None
    reason = event.data.get("start_scenario_reason")
    if not isinstance(reason, dict):
        return None
    type_ = reason.get("type")
    return str(type_) if type_ else None


class IntentDispatcher:
    """Fetch scenario event log → fire ``sberhome_intent`` HA events.

    DI: hass (task creation + event bus), client-getter (SberClient может
    быть lazy у координатора), state_cache (homes), listener_registry-getter
    (registry подменяется YAML-reload'ом после init).
    """

    def __init__(
        self,
        hass: HomeAssistant,
        get_client: Callable[[], SberClient],
        state_cache: StateCache,
        get_listener_registry: Callable[[], ListenerRegistry],
    ) -> None:
        self._hass = hass
        self._get_client = get_client
        self._state_cache = state_cache
        self._get_listener_registry = get_listener_registry
        # Cursor per home_id — aware datetime последнего fired event'а.
        self._last_event_time: dict[str, datetime | None] = {}
        # Dedup по event_id.
        self._fired_event_ids: deque[str] = deque(maxlen=INTENT_DEDUP_HISTORY)
        # Coalesce-flag worker.
        self._pending: bool = False
        self._task: asyncio.Task | None = None
        # Safety-net poller.
        self._poller_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API (для coordinator)
    # ------------------------------------------------------------------
    def request_dispatch(self) -> None:
        """Trigger a dispatch pass (coalesced).

        Ставит pending флаг и стартует worker task если не запущен.
        Многократные вызовы во время работающего worker'а не создают
        лишних task'ов — worker увидит pending и сделает ещё проход.
        Весь метод синхронный (без await) → атомарен в event loop.
        """
        self._pending = True
        if self._task is None or self._task.done():
            self._task = self._hass.async_create_task(self._worker())

    def start_poller(self) -> None:
        """Запустить safety-net poller (idempotent)."""
        if self._poller_task is not None and not self._poller_task.done():
            return
        try:
            self._poller_task = self._hass.async_create_background_task(
                self._poller_loop(),
                name=f"{DOMAIN}_intent_poller",
            )
            LOGGER.debug("intent poller task scheduled")
        except Exception:  # pragma: no cover — defensive
            LOGGER.exception("Failed to schedule intent poller task")

    async def async_shutdown(self) -> None:
        """Остановить poller и дождаться worker'а (bounded)."""
        import contextlib

        if self._poller_task is not None:
            self._poller_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._poller_task
        if self._task is not None and not self._task.done():
            # Не отменяем — worker сам завершится когда pending опустится.
            # Если завис — timeout, task-зомби, но HA-shutdown продолжится.
            with contextlib.suppress(TimeoutError, asyncio.CancelledError, Exception):
                await asyncio.wait_for(self._task, timeout=5.0)

    # ------------------------------------------------------------------
    # Worker / poller
    # ------------------------------------------------------------------
    async def _worker(self) -> None:
        """Loop: fetch + fire пока приходят новые pending-request'ы."""
        while self._pending:
            self._pending = False
            homes = self._state_cache.get_homes()
            if not homes:
                LOGGER.debug("intent dispatch requested, но state_cache без homes — пропуск")
                continue
            for home in homes:
                if not home.id:
                    continue
                try:
                    await self._dispatch_home(home.id)
                except Exception:  # noqa: BLE001 — best-effort per home
                    LOGGER.debug(
                        "intent dispatch failed for home %s (ignored)",
                        home.id,
                        exc_info=True,
                    )

    async def _poller_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(INTENT_POLLER_INTERVAL_SEC)
                self.request_dispatch()
        except asyncio.CancelledError:
            raise

    async def _dispatch_home(self, home_id: str) -> None:
        """Один цикл fetch → filter → dedup → fire для одного дома."""
        try:
            events = await self._get_client().scenarios.history(home_id, limit=INTENT_FETCH_LIMIT)
        except Exception:  # noqa: BLE001
            LOGGER.debug("Failed to fetch scenario history for home %s", home_id, exc_info=True)
            return
        new_events = self._select_new_events(home_id, events)
        if not new_events:
            return

        if len(new_events) >= INTENT_FETCH_LIMIT:
            LOGGER.warning(
                "intent dispatch: fetched %d new events for home %s (== limit) — "
                "могли остаться необработанные старые события, увеличьте "
                "INTENT_FETCH_LIMIT если такое повторяется",
                len(new_events),
                home_id,
            )

        fired_events: list[ScenarioEventDto] = []
        for event in new_events:
            if event.id and event.id in self._fired_event_ids:
                LOGGER.debug("Skipping already-fired intent event %s", event.id)
                continue
            if event.id:
                self._fired_event_ids.append(event.id)
            self.fire_event(event, home_id_hint=home_id)
            fired_events.append(event)

        if not fired_events:
            return

        fired_times = [
            parsed
            for parsed in (parse_event_time(e.event_time) for e in fired_events)
            if parsed is not None
        ]
        if fired_times:
            latest = max(fired_times)
            prev = self._last_event_time.get(home_id)
            if prev is None or latest > prev:
                self._last_event_time[home_id] = latest

    def _select_new_events(
        self, home_id: str, events: list[ScenarioEventDto]
    ) -> list[ScenarioEventDto]:
        """Filter events strictly newer than the per-home cursor.

        При первом push'е (cursor=None) выставляем cursor на now и
        возвращаем [] — событие в логе может быть многочасовой давности.
        Compare как datetime (см. ``parse_event_time``).
        """
        cursor = self._last_event_time.get(home_id)
        if cursor is None:
            self._last_event_time[home_id] = datetime.now(UTC)
            return []
        result: list[ScenarioEventDto] = []
        for e in events:
            parsed = parse_event_time(e.event_time)
            if parsed is None:
                continue
            if parsed > cursor:
                result.append(e)
        return result

    # ------------------------------------------------------------------
    # Fire
    # ------------------------------------------------------------------
    def fire_event(self, event: ScenarioEventDto, home_id_hint: str | None = None) -> None:
        """Fire ``EVENT_SBERHOME_INTENT`` в HA event bus.

        1. Всегда fire base event с ``source="sber_only"``.
        2. Прогоняем через ``listener_registry.find_matching``.
        3. Для каждого matching listener — дополнительный event с
           ``slug=<listener.slug>`` и ``source="listener"``.

        Матчинг wrapped в try/except — exception в matcher НЕ блокирует
        base event.

        ``home_id_hint`` — home_id из контекста dispatcher'а (Sber часто
        отдаёт `event.home_id = ""` — issue #35 bug #5).
        """
        trigger_type = extract_trigger_type(event)
        home_id = home_id_hint or (event.home_id or None)

        base_data: dict[str, Any] = {
            "slug": None,
            "source": EVENT_SOURCE_SBER_ONLY,
            "name": (event.name or "").strip(),
            "scenario_id": event.object_id,
            "event_time": event.event_time,
            "type": event.type,
            "trigger_type": trigger_type,
            "home_id": home_id,
            "account_id": event.account_id,
            "event_id": event.id,
            "description": event.description or None,
        }
        LOGGER.debug("Firing %s base with data=%s", EVENT_SBERHOME_INTENT, base_data)
        self._hass.bus.async_fire(EVENT_SBERHOME_INTENT, base_data)

        try:
            event_meta = EventMeta(
                scenario_id=event.object_id,
                scenario_name=(event.name or "").strip() or None,
                trigger_type=trigger_type,
                home_id=home_id,
            )
            matches = self._get_listener_registry().find_matching(event_meta)
        except Exception:  # noqa: BLE001
            LOGGER.debug("Listener matching raised — base event already fired", exc_info=True)
            return

        for spec in matches:
            listener_data = dict(base_data)
            listener_data["slug"] = spec.slug
            listener_data["source"] = EVENT_SOURCE_LISTENER
            LOGGER.debug(
                "Firing %s for listener %r with slug=%r",
                EVENT_SBERHOME_INTENT,
                spec.name,
                spec.slug,
            )
            self._hass.bus.async_fire(EVENT_SBERHOME_INTENT, listener_data)
            if event.event_time:
                self._get_listener_registry().mark_fired(spec, event.event_time)


__all__ = [
    "EVENT_SBERHOME_INTENT",
    "INTENT_DEDUP_HISTORY",
    "INTENT_FETCH_LIMIT",
    "INTENT_POLLER_INTERVAL_SEC",
    "IntentDispatcher",
    "extract_trigger_type",
    "parse_event_time",
]
