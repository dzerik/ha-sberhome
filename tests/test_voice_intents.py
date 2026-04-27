"""Phase 10 — voice intents dispatcher tests.

Покрывает coordinator-логику обработки `scenario_widgets` WS push'а:
- Первый запуск (cursor=None) ловит ТОЛЬКО самое свежее событие
  (иначе на старте integration'а fire'ится весь history).
- Последующие push'и фильтруют по `event_time > cursor`.
- Дубликат WS push (Sber всегда шлёт UPDATE_WIDGETS парами ×2) ловится
  через `_intent_dispatch_lock` — fetch только один раз.
- `home_id` отсутствует → skip dispatch (graceful no-op).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.scenario import ScenarioEventDto
from custom_components.sberhome.aiosber.dto.union import UnionDto
from custom_components.sberhome.coordinator import (
    EVENT_SBERHOME_INTENT,
    SberHomeCoordinator,
)


def _event(*, time: str, name: str = "Маркер один", sid: str = "sc-1") -> ScenarioEventDto:
    return ScenarioEventDto(
        id=f"e-{time}",
        event_time=time,
        object_id=sid,
        object_type="SCENARIO",
        name=name,
        type="SUCCESS",
    )


def _coord_with_home(home_id: str | None = "home-1") -> MagicMock:
    coord = MagicMock(spec=SberHomeCoordinator)
    # Привязываем приватные методы к реальной реализации, чтобы handler
    # вызывал настоящие select/fire, а не MagicMock-stub'ы.
    coord._select_new_intent_events = lambda events: SberHomeCoordinator._select_new_intent_events(
        coord, events
    )
    coord._fire_intent_event = lambda e: SberHomeCoordinator._fire_intent_event(coord, e)
    coord._last_intent_event_time = None
    coord._intent_dispatch_lock = asyncio.Lock()
    coord.state_cache = MagicMock()
    if home_id is None:
        coord.state_cache.get_home = MagicMock(return_value=None)
    else:
        home = UnionDto(id=home_id)
        coord.state_cache.get_home = MagicMock(return_value=home)
    coord.client = MagicMock()
    coord.client.scenarios = MagicMock()
    coord.client.scenarios.history = AsyncMock()
    coord.hass = MagicMock()
    coord.hass.bus = MagicMock()
    coord.hass.bus.async_fire = MagicMock()
    coord._record_ws_message = MagicMock()
    return coord


# ---------------------------------------------------------------------------
# _select_new_intent_events
# ---------------------------------------------------------------------------


class TestSelectNewIntentEvents:
    def test_first_run_takes_only_head(self):
        """На первом запуске (cursor=None) берём только самое свежее
        событие — иначе fire'ится весь history."""
        coord = _coord_with_home()
        events = [
            _event(time="2026-04-27T12:50:00Z"),
            _event(time="2026-04-27T12:49:00Z"),
            _event(time="2026-04-27T12:48:00Z"),
        ]
        result = SberHomeCoordinator._select_new_intent_events(coord, events)
        assert len(result) == 1
        assert result[0].event_time == "2026-04-27T12:50:00Z"
        # Cursor выставлен, чтобы повторный вызов не сдупликатил head.
        assert coord._last_intent_event_time == "2026-04-27T12:50:00Z"

    def test_cursor_filters_old_events(self):
        coord = _coord_with_home()
        coord._last_intent_event_time = "2026-04-27T12:48:00Z"
        events = [
            _event(time="2026-04-27T12:50:00Z"),
            _event(time="2026-04-27T12:49:00Z"),
            _event(time="2026-04-27T12:48:00Z"),  # = cursor, не должен попасть
            _event(time="2026-04-27T12:47:00Z"),
        ]
        result = SberHomeCoordinator._select_new_intent_events(coord, events)
        times = [e.event_time for e in result]
        assert times == ["2026-04-27T12:50:00Z", "2026-04-27T12:49:00Z"]

    def test_no_new_events(self):
        coord = _coord_with_home()
        coord._last_intent_event_time = "2026-04-27T12:50:00Z"
        events = [_event(time="2026-04-27T12:50:00Z")]
        assert SberHomeCoordinator._select_new_intent_events(coord, events) == []

    def test_empty_response_with_first_run(self):
        coord = _coord_with_home()
        assert SberHomeCoordinator._select_new_intent_events(coord, []) == []
        # Cursor остаётся None — потом первый event подхватим.
        assert coord._last_intent_event_time is None


# ---------------------------------------------------------------------------
# _fire_intent_event — payload shape
# ---------------------------------------------------------------------------


class TestFireIntentEvent:
    def test_emits_minimal_payload(self):
        coord = _coord_with_home()
        SberHomeCoordinator._fire_intent_event(
            coord, _event(time="2026-04-27T12:50:00Z", name="Утренний кофе ", sid="sc-42")
        )
        coord.hass.bus.async_fire.assert_called_once()
        event_type, data = coord.hass.bus.async_fire.call_args[0]
        assert event_type == EVENT_SBERHOME_INTENT
        # Имя trim'нуто (Sber возвращает с trailing space — убираем).
        assert data["name"] == "Утренний кофе"
        assert data["scenario_id"] == "sc-42"
        assert data["event_time"] == "2026-04-27T12:50:00Z"
        assert data["type"] == "SUCCESS"


# ---------------------------------------------------------------------------
# _on_ws_scenario_widgets — full handler
# ---------------------------------------------------------------------------


class TestOnWsScenarioWidgets:
    @pytest.mark.asyncio
    async def test_skips_when_no_home_id(self):
        coord = _coord_with_home(home_id=None)
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={})

        await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        coord.client.scenarios.history.assert_not_awaited()
        coord.hass.bus.async_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_push_fetches_history_and_fires(self):
        coord = _coord_with_home()
        coord.client.scenarios.history = AsyncMock(
            return_value=[_event(time="2026-04-27T12:50:00Z", name="Маркер")]
        )
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={"scenario_widget": {"type": "UPDATE_WIDGETS"}})

        # cooldown=0 для теста чтобы не блокировать на 1 sec
        from custom_components.sberhome import coordinator as coord_mod

        original_cooldown = coord_mod.INTENT_DISPATCH_COOLDOWN_SEC
        coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = 0
        try:
            await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        finally:
            coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = original_cooldown

        coord.client.scenarios.history.assert_awaited_once()
        # Hass event fired для самого свежего события (head на первом запуске).
        coord.hass.bus.async_fire.assert_called_once()
        assert coord._last_intent_event_time == "2026-04-27T12:50:00Z"

    @pytest.mark.asyncio
    async def test_duplicate_push_skipped_by_lock(self):
        """Sber шлёт UPDATE_WIDGETS парами ×2 за <100ms — второй вызов
        попадает на занятый lock, history.fetch вызывается ровно 1 раз."""
        coord = _coord_with_home()

        # history намеренно медленный, чтобы lock держал второй call
        async def slow_history(*args, **kwargs):
            await asyncio.sleep(0.05)
            return [_event(time="2026-04-27T12:50:00Z")]

        coord.client.scenarios.history = AsyncMock(side_effect=slow_history)
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={})

        from custom_components.sberhome import coordinator as coord_mod

        original_cooldown = coord_mod.INTENT_DISPATCH_COOLDOWN_SEC
        coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = 0
        try:
            # Симулируем дублирующий push.
            await asyncio.gather(
                SberHomeCoordinator._on_ws_scenario_widgets(coord, msg),
                SberHomeCoordinator._on_ws_scenario_widgets(coord, msg),
            )
        finally:
            coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = original_cooldown
        # history дёрнулась ОДИН РАЗ — второй WS push скиплен через lock.
        assert coord.client.scenarios.history.await_count == 1

    @pytest.mark.asyncio
    async def test_history_failure_does_not_break_handler(self):
        coord = _coord_with_home()
        coord.client.scenarios.history = AsyncMock(side_effect=RuntimeError("boom"))
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={})

        # Не должно бросать наружу — best-effort.
        await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        coord.hass.bus.async_fire.assert_not_called()
