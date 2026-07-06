"""IntentDispatcher — voice-intent dispatch, вынесенный из coordinator.

Адаптация tests/test_voice_intents.py под standalone-класс: DI вместо
coordinator-полей, публичный API request_dispatch/fire_event/start_poller.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.scenario import ScenarioEventDto
from custom_components.sberhome.aiosber.dto.union import UnionDto
from custom_components.sberhome.intent_dispatcher import (
    EVENT_SBERHOME_INTENT,
    INTENT_FETCH_LIMIT,
    IntentDispatcher,
    extract_trigger_type,
    parse_event_time,
)


def _event(
    *,
    time: str,
    name: str = "Маркер один",
    sid: str = "sc-1",
    home_id: str = "",
    event_id: str | None = None,
) -> ScenarioEventDto:
    return ScenarioEventDto(
        id=event_id if event_id is not None else f"e-{time}",
        event_time=time,
        object_id=sid,
        object_type="SCENARIO",
        name=name,
        type="SUCCESS",
        home_id=home_id,
    )


def _dispatcher(home_ids: list[str] | None = None) -> tuple[IntentDispatcher, MagicMock]:
    """Собрать dispatcher с mock-зависимостями. Возвращает (dispatcher, env).

    env.hass / env.client / env.state_cache / env.registry — для asserts.
    """
    env = MagicMock()
    env.hass.async_create_task = lambda coro: asyncio.create_task(coro)
    env.hass.bus.async_fire = MagicMock()
    env.client.scenarios.history = AsyncMock(return_value=[])
    homes = [UnionDto(id=hid) for hid in (home_ids if home_ids is not None else ["home-1"])]
    env.state_cache.get_homes = MagicMock(return_value=homes)
    env.registry.find_matching = MagicMock(return_value=[])
    disp = IntentDispatcher(
        hass=env.hass,
        get_client=lambda: env.client,
        state_cache=env.state_cache,
        get_listener_registry=lambda: env.registry,
    )
    return disp, env


# ---------------------------------------------------------------------------
# parse_event_time — краевые случаи ISO-форматов Sber
# ---------------------------------------------------------------------------


class TestParseEventTime:
    def test_parses_Z_suffix(self):
        result = parse_event_time("2026-04-27T12:44:49.430277Z")
        assert result is not None
        assert result.utcoffset().total_seconds() == 0

    def test_Z_and_offset_compare_equal(self):
        z = parse_event_time("2026-04-27T12:44:49.430277Z")
        offset = parse_event_time("2026-04-27T12:44:49.430277+00:00")
        assert z == offset

    def test_trimmed_fraction_orders_correctly(self):
        earlier = parse_event_time("2026-04-27T12:44:49.43Z")
        later = parse_event_time("2026-04-27T12:44:49.430277Z")
        assert earlier < later

    def test_missing_and_invalid_return_none(self):
        assert parse_event_time(None) is None
        assert parse_event_time("") is None
        assert parse_event_time("garbage") is None


# ---------------------------------------------------------------------------
# _select_new_events / cursor
# ---------------------------------------------------------------------------


class TestSelectNewEvents:
    def test_first_run_sets_cursor_to_now_without_firing(self):
        disp, _ = _dispatcher()
        events = [_event(time="2026-04-27T12:50:00Z")]
        assert disp._select_new_events("home-1", events) == []
        cursor = disp._last_event_time["home-1"]
        assert isinstance(cursor, datetime)
        assert cursor > parse_event_time("2026-04-27T12:50:00Z")

    def test_cursor_filters_old_events(self):
        disp, _ = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-04-27T12:48:00Z")
        events = [
            _event(time="2026-04-27T12:50:00Z"),
            _event(time="2026-04-27T12:48:00Z"),  # == cursor → отсечён
            _event(time="2026-04-27T12:47:00Z"),
        ]
        result = disp._select_new_events("home-1", events)
        assert [e.event_time for e in result] == ["2026-04-27T12:50:00Z"]

    def test_events_with_invalid_time_skipped(self):
        disp, _ = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-04-27T12:00:00Z")
        events = [
            _event(time="garbage"),
            _event(time="2026-04-27T12:50:00Z"),
        ]
        result = disp._select_new_events("home-1", events)
        assert [e.event_time for e in result] == ["2026-04-27T12:50:00Z"]

    def test_per_home_cursor_independent(self):
        disp, _ = _dispatcher(["home-main", "home-dacha"])
        disp._last_event_time["home-main"] = parse_event_time("2026-04-27T15:00:00Z")
        result = disp._select_new_events("home-dacha", [_event(time="2026-04-27T13:00:00Z")])
        assert result == []
        assert disp._last_event_time["home-main"] == parse_event_time("2026-04-27T15:00:00Z")


# ---------------------------------------------------------------------------
# fire_event
# ---------------------------------------------------------------------------


class TestFireEvent:
    def test_home_id_hint_overrides_empty_event_home_id(self):
        disp, env = _dispatcher()
        disp.fire_event(_event(time="2026-04-27T12:50:00Z", home_id=""), home_id_hint="hint")
        _, data = env.hass.bus.async_fire.call_args[0]
        assert data["home_id"] == "hint"

    def test_fallback_to_event_home_id(self):
        disp, env = _dispatcher()
        disp.fire_event(_event(time="2026-04-27T12:50:00Z", home_id="ev-home"))
        _, data = env.hass.bus.async_fire.call_args[0]
        assert data["home_id"] == "ev-home"

    def test_emits_payload_shape(self):
        disp, env = _dispatcher()
        disp.fire_event(
            _event(time="2026-04-27T12:50:00Z", name="Утренний кофе ", sid="sc-42"),
            home_id_hint="home-1",
        )
        event_type, data = env.hass.bus.async_fire.call_args[0]
        assert event_type == EVENT_SBERHOME_INTENT
        assert data["name"] == "Утренний кофе"  # trimmed
        assert data["scenario_id"] == "sc-42"
        assert data["type"] == "SUCCESS"
        assert data["slug"] is None

    def test_listener_match_fires_extra_event(self):
        disp, env = _dispatcher()
        spec = MagicMock()
        spec.slug = "my-slug"
        spec.name = "My listener"
        env.registry.find_matching = MagicMock(return_value=[spec])
        disp.fire_event(_event(time="2026-04-27T12:50:00Z"), home_id_hint="home-1")
        assert env.hass.bus.async_fire.call_count == 2  # base + listener
        _, listener_data = env.hass.bus.async_fire.call_args_list[1][0]
        assert listener_data["slug"] == "my-slug"
        env.registry.mark_fired.assert_called_once()

    def test_listener_matching_error_does_not_block_base(self):
        disp, env = _dispatcher()
        env.registry.find_matching = MagicMock(side_effect=RuntimeError("boom"))
        disp.fire_event(_event(time="2026-04-27T12:50:00Z"))
        env.hass.bus.async_fire.assert_called_once()  # base всё равно fired


# ---------------------------------------------------------------------------
# Coalesce-flag worker + dedup
# ---------------------------------------------------------------------------


class TestDispatchWorker:
    @pytest.mark.asyncio
    async def test_first_push_does_not_fire_historical_event(self):
        disp, env = _dispatcher()
        env.client.scenarios.history = AsyncMock(return_value=[_event(time="2026-04-27T12:50:00Z")])
        disp.request_dispatch()
        await disp._task
        env.hass.bus.async_fire.assert_not_called()
        assert disp._last_event_time["home-1"] > parse_event_time("2026-04-27T12:50:00Z")

    @pytest.mark.asyncio
    async def test_subsequent_push_fires_new_event(self):
        disp, env = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-04-27T12:00:00Z")
        env.client.scenarios.history = AsyncMock(return_value=[_event(time="2026-04-27T12:50:00Z")])
        disp.request_dispatch()
        await disp._task
        env.hass.bus.async_fire.assert_called_once()
        assert disp._last_event_time["home-1"] == parse_event_time("2026-04-27T12:50:00Z")

    @pytest.mark.asyncio
    async def test_distinct_push_during_dispatch_coalesces(self):
        """Distinct push во время dispatch'а НЕ теряется (issue #35 bug #1)."""
        disp, env = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-04-27T12:00:00Z")

        call_num = 0

        async def history_stub(*args, **kwargs):
            nonlocal call_num
            call_num += 1
            if call_num == 1:
                await asyncio.sleep(0.02)
                return [_event(time="2026-04-27T12:30:00Z", sid="sc-1", event_id="e-1")]
            return [_event(time="2026-04-27T12:31:00Z", sid="sc-2", event_id="e-2")]

        env.client.scenarios.history = AsyncMock(side_effect=history_stub)

        disp.request_dispatch()
        await asyncio.sleep(0)
        disp.request_dispatch()  # приходит пока worker в первом fetch'е
        await disp._task

        assert env.client.scenarios.history.await_count == 2
        assert env.hass.bus.async_fire.call_count == 2

    @pytest.mark.asyncio
    async def test_paired_push_same_event_deduped(self):
        """Sber шлёт push парами — event_id dedup блокирует второй fire."""
        disp, env = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-04-27T12:00:00Z")
        env.client.scenarios.history = AsyncMock(
            return_value=[_event(time="2026-04-27T12:50:00Z", event_id="dup")]
        )
        disp.request_dispatch()
        await asyncio.sleep(0)
        disp.request_dispatch()
        await disp._task
        env.hass.bus.async_fire.assert_called_once()

    @pytest.mark.asyncio
    async def test_saturation_warning(self, caplog):
        disp, env = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-04-27T00:00:00Z")
        events = [
            _event(time=f"2026-04-27T12:{m:02d}:00Z", event_id=f"e-{m}")
            for m in range(INTENT_FETCH_LIMIT)
        ]
        env.client.scenarios.history = AsyncMock(return_value=events)
        with caplog.at_level("WARNING", logger="custom_components.sberhome"):
            disp.request_dispatch()
            await disp._task
        assert any("могли остаться необработанные" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_home_failure_does_not_block_other(self):
        disp, env = _dispatcher(["home-a", "home-b"])
        disp._last_event_time["home-a"] = parse_event_time("2026-04-27T00:00:00Z")
        disp._last_event_time["home-b"] = parse_event_time("2026-04-27T00:00:00Z")

        def by_home(home_id, **kwargs):
            if home_id == "home-a":
                raise RuntimeError("boom")
            return [_event(time="2026-04-27T13:00:00Z", sid="sc-b", event_id="e-b")]

        env.client.scenarios.history = AsyncMock(side_effect=by_home)
        disp.request_dispatch()
        await disp._task
        env.hass.bus.async_fire.assert_called_once()
        assert env.hass.bus.async_fire.call_args[0][1]["scenario_id"] == "sc-b"

    @pytest.mark.asyncio
    async def test_no_homes_is_noop(self):
        disp, env = _dispatcher([])
        disp.request_dispatch()
        await disp._task
        env.client.scenarios.history.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_only_one_worker_task(self):
        disp, env = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-04-27T12:00:00Z")
        started = asyncio.Event()

        async def slow_history(*args, **kwargs):
            started.set()
            await asyncio.sleep(0.05)
            return []

        env.client.scenarios.history = AsyncMock(side_effect=slow_history)
        disp.request_dispatch()
        first = disp._task
        await started.wait()
        disp.request_dispatch()
        disp.request_dispatch()
        assert disp._task is first
        await first


# ---------------------------------------------------------------------------
# Poller lifecycle
# ---------------------------------------------------------------------------


class TestDispatchSourceDiagnostics:
    """v5.12.1 (issue #35): worker логирует источник прохода (ws-push/poller).

    Задержка ~30 сек у пользователя = события ловит только safety-net
    poller; по trigger= в DEBUG-логе это теперь видно без гаданий.
    """

    @pytest.mark.asyncio
    async def test_trigger_source_passed_to_dispatch_home(self):
        disp, env = _dispatcher()
        disp._dispatch_home = AsyncMock()
        disp.request_dispatch(source="poller")
        await disp._task
        disp._dispatch_home.assert_awaited_once_with("home-1", trigger="poller")

    @pytest.mark.asyncio
    async def test_coalesced_sources_merged_and_cleared(self):
        """WS push + poller во время одного pending → оба источника в trigger."""
        disp, env = _dispatcher()
        seen: list[str] = []

        async def dispatch_stub(home_id, trigger="unknown"):
            seen.append(trigger)

        disp._dispatch_home = dispatch_stub
        disp._pending = True
        disp._pending_sources = {"ws-push", "poller"}
        await disp._worker()
        assert seen == ["poller,ws-push"]
        assert disp._pending_sources == set()

    @pytest.mark.asyncio
    async def test_default_source_is_ws_push(self):
        disp, env = _dispatcher()
        disp._dispatch_home = AsyncMock()
        disp.request_dispatch()
        await disp._task
        disp._dispatch_home.assert_awaited_once_with("home-1", trigger="ws-push")


class TestPoller:
    @pytest.mark.asyncio
    async def test_poller_triggers_dispatch(self):
        from custom_components.sberhome import intent_dispatcher as mod

        disp, env = _dispatcher()
        original = mod.INTENT_POLLER_INTERVAL_SEC
        mod.INTENT_POLLER_INTERVAL_SEC = 0.01
        try:
            task = asyncio.create_task(disp._poller_loop())
            await asyncio.sleep(0.05)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        finally:
            mod.INTENT_POLLER_INTERVAL_SEC = original
        assert disp._pending or disp._task is not None

    @pytest.mark.asyncio
    async def test_shutdown_cancels_poller_and_waits_worker(self):
        disp, env = _dispatcher()
        # Запустим worker, который быстро завершится.
        disp.request_dispatch()
        # Poller через create_task-совместимый mock.
        env.hass.async_create_background_task = lambda coro, name=None: asyncio.create_task(coro)
        disp.start_poller()
        await disp.async_shutdown()
        assert disp._poller_task.cancelled() or disp._poller_task.done()


# ---------------------------------------------------------------------------
# fire_event + РЕАЛЬНЫЙ ListenerRegistry (end-to-end, портировано из
# test_coordinator.py)
# ---------------------------------------------------------------------------


class TestFireEventWithRealRegistry:
    def _dispatcher_with_registry(self, registry):
        env = MagicMock()
        env.hass.bus.async_fire = MagicMock()
        return (
            IntentDispatcher(
                hass=env.hass,
                get_client=lambda: env.client,
                state_cache=env.state_cache,
                get_listener_registry=lambda: registry,
            ),
            env,
        )

    def _time_event(self, sid: str = "sc-1", name: str = "Доброе утро") -> ScenarioEventDto:
        return ScenarioEventDto(
            id=f"evt-{sid}",
            event_time="2026-05-13T08:00:00+00:00",
            object_id=sid,
            object_type="SCENARIO",
            name=name,
            home_id="home-1",
            data={"start_scenario_reason": {"type": "TIME"}},
        )

    def test_match_fires_additional_event_with_slug(self):
        from custom_components.sberhome.listeners import (
            ListenerFilter,
            ListenerRegistry,
            ListenerSpec,
        )

        registry = ListenerRegistry(
            [
                ListenerSpec(
                    slug="any_time",
                    name="Any TIME",
                    filter=ListenerFilter(trigger_types=frozenset({"TIME"})),
                )
            ]
        )
        disp, env = self._dispatcher_with_registry(registry)
        disp.fire_event(self._time_event())

        calls = env.hass.bus.async_fire.call_args_list
        assert len(calls) == 2
        base, listener_evt = calls[0].args[1], calls[1].args[1]
        assert base["source"] == "sber_only" and base["slug"] is None
        assert listener_evt["source"] == "listener"
        assert listener_evt["slug"] == "any_time"
        assert listener_evt["trigger_type"] == "TIME"

    def test_no_match_only_base_event(self):
        from custom_components.sberhome.listeners import (
            ListenerFilter,
            ListenerRegistry,
            ListenerSpec,
        )

        registry = ListenerRegistry(
            [
                ListenerSpec(
                    slug="phrases_only",
                    name="X",
                    filter=ListenerFilter(trigger_types=frozenset({"PHRASES"})),
                )
            ]
        )
        disp, env = self._dispatcher_with_registry(registry)
        disp.fire_event(self._time_event())
        env.hass.bus.async_fire.assert_called_once()
        assert env.hass.bus.async_fire.call_args.args[1]["source"] == "sber_only"

    def test_match_updates_last_fired_at(self):
        from custom_components.sberhome.listeners import (
            ListenerFilter,
            ListenerRegistry,
            ListenerSpec,
        )

        spec = ListenerSpec(
            slug="any_time",
            name="Any TIME",
            filter=ListenerFilter(trigger_types=frozenset({"TIME"})),
        )
        disp, env = self._dispatcher_with_registry(ListenerRegistry([spec]))
        assert spec.last_fired_at is None
        disp.fire_event(self._time_event())
        assert spec.last_fired_at == "2026-05-13T08:00:00+00:00"


# ---------------------------------------------------------------------------
# extract_trigger_type (портировано из test_voice_intents.py)
# ---------------------------------------------------------------------------


class TestExtractTriggerType:
    def test_phrases_for_voice(self):
        event = ScenarioEventDto(
            id="e-1",
            event_time="2026-05-13T08:00:00Z",
            data={"start_scenario_reason": {"type": "PHRASES", "time_data": None}},
        )
        assert extract_trigger_type(event) == "PHRASES"

    def test_time_for_schedule(self):
        event = ScenarioEventDto(
            id="e-2",
            data={"start_scenario_reason": {"type": "TIME", "time_data": {"execute_at": "08:00"}}},
        )
        assert extract_trigger_type(event) == "TIME"

    def test_malformed_data_returns_none(self):
        assert extract_trigger_type(ScenarioEventDto(id="x", data="garbage")) is None
        assert extract_trigger_type(ScenarioEventDto(id="x", data={"other": 1})) is None
        assert (
            extract_trigger_type(ScenarioEventDto(id="x", data={"start_scenario_reason": "x"}))
            is None
        )
        assert (
            extract_trigger_type(ScenarioEventDto(id="x", data={"start_scenario_reason": {}}))
            is None
        )

    def test_trigger_type_in_fired_payload(self):
        disp, env = _dispatcher()
        event = ScenarioEventDto(
            id="e-3",
            event_time="2026-05-13T08:00:00Z",
            object_id="sc-1",
            name="Голосовой",
            type="SUCCESS",
            data={"start_scenario_reason": {"type": "PHRASES"}},
        )
        disp.fire_event(event, home_id_hint="home-1")
        _, data = env.hass.bus.async_fire.call_args[0]
        assert data["trigger_type"] == "PHRASES"


# ---------------------------------------------------------------------------
# Regression — issue #35 (портировано из test_voice_intents.py)
# ---------------------------------------------------------------------------


class TestRegressionIssue35:
    @pytest.mark.asyncio
    async def test_two_distinct_commands_arriving_close_together(self):
        """Две команды подряд: обе fired, ни одна не потеряна
        (drop через asyncio.Lock — bug #1 до v5.10.8)."""
        disp, env = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-06-28T00:00:00Z")

        cmd1 = _event(time="2026-06-28T15:47:00Z", sid="sc-cmd1", event_id="evt-cmd1")
        cmd2 = _event(time="2026-06-28T15:47:15Z", sid="sc-cmd2", event_id="evt-cmd2")

        call_num = 0
        started1 = asyncio.Event()

        async def history_stub(*args, **kwargs):
            nonlocal call_num
            call_num += 1
            started1.set()
            if call_num == 1:
                await asyncio.sleep(0.02)
                return [cmd1]
            return [cmd2, cmd1]

        env.client.scenarios.history = AsyncMock(side_effect=history_stub)

        disp.request_dispatch()
        await started1.wait()
        disp.request_dispatch()  # приходит пока worker в первом fetch'е
        await disp._task

        fired = {c.args[1]["scenario_id"] for c in env.hass.bus.async_fire.call_args_list}
        assert fired == {"sc-cmd1", "sc-cmd2"}
        assert env.hass.bus.async_fire.call_count == 2  # dedup: cmd1 один раз

    @pytest.mark.asyncio
    async def test_panov_automation_shape_no_duplicate_name(self):
        """Батч из реального лога @PanovEduard: Balcony_temp + surrogate
        в одном fetch'е — каждый fired ровно один раз (mode:single в его
        HA-automation не получает «Already running»)."""
        disp, env = _dispatcher()
        disp._last_event_time["home-1"] = parse_event_time("2026-06-30T00:00:00Z")

        balcony = _event(
            time="2026-06-30T22:16:15.960325Z",
            sid="6a2b2bca053903eb5be4c02e",
            event_id="6a44402faf5871ea63265e20",
            name="Balcony_temp",
        )
        surrogate = _event(
            time="2026-06-30T22:16:16.601131Z",
            sid="6a2caab2053903eb5be6bcbc",
            event_id="6a444030d70c79d108db2c2f",
            name="Sber TTS surrogate (Мой дом) [home_id=d8ktpv4f]",
        )
        env.client.scenarios.history = AsyncMock(return_value=[surrogate, balcony])

        disp.request_dispatch()
        await asyncio.sleep(0)
        disp.request_dispatch()  # paired push
        await disp._task

        fired_names = [c.args[1]["name"] for c in env.hass.bus.async_fire.call_args_list]
        assert fired_names.count("Balcony_temp") == 1
        assert fired_names.count("Sber TTS surrogate (Мой дом) [home_id=d8ktpv4f]") == 1
        assert env.hass.bus.async_fire.call_count == 2
