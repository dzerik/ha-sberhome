"""Phase 10 — voice intents dispatcher tests.

Покрывает coordinator-логику обработки `scenario_widgets` WS push'а:
- Первый запуск (cursor=None) НЕ фаерит ничего и выставляет cursor=now
  (issue #35; раньше брали `events[0]` из истории и могли зафаерить
  событие многочасовой давности).
- Последующие push'и фильтруют по `event_time > cursor`.
- Дубликат WS push (Sber всегда шлёт UPDATE_WIDGETS парами ×2) ловится
  через `_intent_dispatch_lock` — fetch только один раз.
- Dedup по event_id: повторный fetch одного и того же event'а не фаерит
  его дважды (issue #35).
- `home_id` отсутствует → skip dispatch (graceful no-op).
"""

from __future__ import annotations

import asyncio
from collections import deque
from unittest.mock import AsyncMock, MagicMock, patch

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
    """Mock-координатор для single-home сценариев (legacy bc)."""
    return _coord_with_homes([home_id] if home_id else [])


def _coord_with_homes(home_ids: list[str]) -> MagicMock:
    """Mock-координатор для multi-home сценариев.

    Принимает список home_id. Пустой список = no homes (skip dispatch).
    """
    coord = MagicMock(spec=SberHomeCoordinator)
    coord._select_new_intent_events = lambda home_id, events: (
        SberHomeCoordinator._select_new_intent_events(coord, home_id, events)
    )
    coord._fetch_new_intent_events = lambda home_id: SberHomeCoordinator._fetch_new_intent_events(
        coord, home_id
    )
    coord._fire_intent_event = lambda e: SberHomeCoordinator._fire_intent_event(coord, e)
    coord._last_intent_event_time = {}
    coord._fired_event_ids = deque(maxlen=64)
    coord._intent_dispatch_lock = asyncio.Lock()
    coord._intent_dispatch_cooldown_until = 0.0
    coord.state_cache = MagicMock()
    homes = [UnionDto(id=hid) for hid in home_ids]
    coord.state_cache.get_homes = MagicMock(return_value=homes)
    coord.state_cache.get_home = MagicMock(return_value=homes[0] if homes else None)
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
    def test_first_run_sets_cursor_to_now_without_firing(self):
        """issue #35: на первом запуске (cursor=None) НЕ фаерим ничего —
        cursor выставляется на now, реальный event прилетит со следующим
        push'ом. Раньше брали head из истории — это могло зафаерить
        событие многочасовой давности."""
        coord = _coord_with_home()
        events = [
            _event(time="2026-04-27T12:50:00Z"),
            _event(time="2026-04-27T12:49:00Z"),
            _event(time="2026-04-27T12:48:00Z"),
        ]
        result = SberHomeCoordinator._select_new_intent_events(coord, "home-1", events)
        assert result == []
        # Cursor выставлен на now (значительно позже всех historical events).
        cursor = coord._last_intent_event_time["home-1"]
        assert cursor is not None
        assert cursor > "2026-04-27T12:50:00Z"

    def test_cursor_filters_old_events(self):
        coord = _coord_with_home()
        coord._last_intent_event_time["home-1"] = "2026-04-27T12:48:00Z"
        events = [
            _event(time="2026-04-27T12:50:00Z"),
            _event(time="2026-04-27T12:49:00Z"),
            _event(time="2026-04-27T12:48:00Z"),  # = cursor, не должен попасть
            _event(time="2026-04-27T12:47:00Z"),
        ]
        result = SberHomeCoordinator._select_new_intent_events(coord, "home-1", events)
        times = [e.event_time for e in result]
        assert times == ["2026-04-27T12:50:00Z", "2026-04-27T12:49:00Z"]

    def test_no_new_events(self):
        coord = _coord_with_home()
        coord._last_intent_event_time["home-1"] = "2026-04-27T12:50:00Z"
        events = [_event(time="2026-04-27T12:50:00Z")]
        assert SberHomeCoordinator._select_new_intent_events(coord, "home-1", events) == []

    def test_empty_response_with_first_run(self):
        """issue #35: cursor=None + пустой ответ → cursor всё равно
        выставляется на now (иначе следующий push снова прочитает
        historical events как «свежие»)."""
        coord = _coord_with_home()
        assert SberHomeCoordinator._select_new_intent_events(coord, "home-1", []) == []
        # Cursor выставлен на now — фиксирует timestamp начала наблюдения.
        cursor = coord._last_intent_event_time["home-1"]
        assert cursor is not None
        assert cursor > "2026-01-01T00:00:00Z"

    def test_per_home_cursor_independent(self):
        """Multi-home: cursor одного дома не влияет на cursor другого.

        Сценарий: события в «Даче» с T2 < cursor «Мой дом» T1 не должны
        теряться (баг которого мы избегаем глобальным cursor'ом).
        """
        coord = _coord_with_homes(["home-main", "home-dacha"])
        coord._last_intent_event_time["home-main"] = "2026-04-27T15:00:00Z"
        # События в «Даче» — старше cursor'а из «Мой дом».
        dacha_events = [
            _event(time="2026-04-27T13:00:00Z"),
            _event(time="2026-04-27T12:00:00Z"),
        ]
        result = SberHomeCoordinator._select_new_intent_events(coord, "home-dacha", dacha_events)
        # issue #35: первый push в «Даче» (cursor unset) → cursor=now,
        # ничего не фаерим — historical events не должны лететь как
        # «свежие».
        assert result == []
        assert coord._last_intent_event_time["home-dacha"] is not None
        assert coord._last_intent_event_time["home-dacha"] > "2026-04-27T13:00:00Z"
        # Cursor «Мой дом» не затронут.
        assert coord._last_intent_event_time["home-main"] == "2026-04-27T15:00:00Z"


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
        # v5.3.0: расширенный payload — добавлены trigger_type, home_id,
        # event_id, description. Без data → trigger_type = None.
        assert data["trigger_type"] is None
        assert data["event_id"] == "e-2026-04-27T12:50:00Z"
        assert "home_id" in data
        assert "description" in data

    def test_emits_trigger_type_phrases_for_voice(self):
        """Голосовое срабатывание — trigger_type='PHRASES'."""
        coord = _coord_with_home()
        event = ScenarioEventDto(
            id="e-1",
            event_time="2026-05-13T08:00:00Z",
            object_id="sc-morning",
            name="Доброе утро",
            type="SUCCESS",
            data={
                "scenario_cancel_time": None,
                "start_scenario_reason": {
                    "type": "PHRASES",
                    "time_data": None,
                },
            },
        )
        SberHomeCoordinator._fire_intent_event(coord, event)
        _, data = coord.hass.bus.async_fire.call_args[0]
        assert data["trigger_type"] == "PHRASES"

    def test_emits_trigger_type_time_for_schedule(self):
        """Расписание — trigger_type='TIME'."""
        coord = _coord_with_home()
        event = ScenarioEventDto(
            id="e-2",
            event_time="2026-05-13T08:00:00Z",
            object_id="sc-timer",
            name="Утренний таймер",
            type="SUCCESS",
            data={
                "start_scenario_reason": {
                    "type": "TIME",
                    "time_data": {"execute_at": "08:00", "rrule": "FREQ=DAILY"},
                },
            },
        )
        SberHomeCoordinator._fire_intent_event(coord, event)
        _, data = coord.hass.bus.async_fire.call_args[0]
        assert data["trigger_type"] == "TIME"

    def test_emits_home_id(self):
        coord = _coord_with_home()
        event = ScenarioEventDto(
            id="e-3",
            event_time="2026-05-13T08:00:00Z",
            object_id="sc-1",
            name="X",
            type="SUCCESS",
            home_id="home-dacha",
        )
        SberHomeCoordinator._fire_intent_event(coord, event)
        _, data = coord.hass.bus.async_fire.call_args[0]
        assert data["home_id"] == "home-dacha"

    def test_malformed_data_returns_none_trigger_type(self):
        """Если data корявая (не dict / без reason) — trigger_type=None, не падаем."""
        from custom_components.sberhome.coordinator import _extract_trigger_type

        # data не dict
        e1 = ScenarioEventDto(id="x", data="garbage")
        assert _extract_trigger_type(e1) is None

        # data без reason
        e2 = ScenarioEventDto(id="x", data={"some_other_field": 1})
        assert _extract_trigger_type(e2) is None

        # reason не dict
        e3 = ScenarioEventDto(id="x", data={"start_scenario_reason": "x"})
        assert _extract_trigger_type(e3) is None

        # reason без type
        e4 = ScenarioEventDto(id="x", data={"start_scenario_reason": {}})
        assert _extract_trigger_type(e4) is None


# ---------------------------------------------------------------------------
# _on_ws_scenario_widgets — full handler
# ---------------------------------------------------------------------------


class TestOnWsScenarioWidgets:
    @pytest.mark.asyncio
    async def test_skips_when_no_homes(self):
        coord = _coord_with_home(home_id=None)
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={})

        await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        coord.client.scenarios.history.assert_not_awaited()
        coord.hass.bus.async_fire.assert_not_called()

    @pytest.mark.asyncio
    async def test_first_push_does_not_fire_history(self):
        """issue #35: первый push после рестарта НЕ фаерит historical event.
        Cursor выставляется на now; реальный event ловится со следующего push'а.
        """
        coord = _coord_with_home()
        coord.client.scenarios.history = AsyncMock(
            return_value=[_event(time="2026-04-27T12:50:00Z", name="Маркер")]
        )
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={"scenario_widget": {"type": "UPDATE_WIDGETS"}})

        from custom_components.sberhome import coordinator as coord_mod

        original_cooldown = coord_mod.INTENT_DISPATCH_COOLDOWN_SEC
        coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = 0
        try:
            with patch(
                "custom_components.sberhome.coordinator.asyncio.sleep",
                AsyncMock(),
            ):
                await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        finally:
            coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = original_cooldown

        # history может быть дёрнута до двух раз (retry на лаг event-log).
        assert coord.client.scenarios.history.await_count >= 1
        # Главное — НИЧЕГО не зафаерили.
        coord.hass.bus.async_fire.assert_not_called()
        # Cursor выставлен на now, не на historical event_time.
        assert coord._last_intent_event_time["home-1"] > "2026-04-27T12:50:00Z"

    @pytest.mark.asyncio
    async def test_subsequent_push_fires_new_event(self):
        """С установленным cursor'ом push с реально свежим event'ом
        фаерит его и продвигает cursor."""
        coord = _coord_with_home()
        coord._last_intent_event_time["home-1"] = "2026-04-27T12:00:00Z"
        coord.client.scenarios.history = AsyncMock(
            return_value=[_event(time="2026-04-27T12:50:00Z", name="Маркер")]
        )
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={})

        from custom_components.sberhome import coordinator as coord_mod

        original_cooldown = coord_mod.INTENT_DISPATCH_COOLDOWN_SEC
        coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = 0
        try:
            await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        finally:
            coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = original_cooldown

        coord.hass.bus.async_fire.assert_called_once()
        assert coord._last_intent_event_time["home-1"] == "2026-04-27T12:50:00Z"

    @pytest.mark.asyncio
    async def test_multi_home_fires_per_home(self):
        """Multi-home: события из каждого дома обрабатываются независимо.

        2 дома, по одному event'у в каждом → 2 history fetch'а, 2 fire.
        Cursors pre-seeded (иначе по issue #35 first-push не фаерит).
        """
        coord = _coord_with_homes(["home-main", "home-dacha"])
        coord._last_intent_event_time["home-main"] = "2026-04-27T00:00:00Z"
        coord._last_intent_event_time["home-dacha"] = "2026-04-27T00:00:00Z"

        def history_by_home(home_id, **kwargs):
            if home_id == "home-main":
                return [_event(time="2026-04-27T15:00:00Z", sid="sc-main")]
            if home_id == "home-dacha":
                return [_event(time="2026-04-27T13:00:00Z", sid="sc-dacha")]
            return []

        coord.client.scenarios.history = AsyncMock(side_effect=history_by_home)
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={})

        from custom_components.sberhome import coordinator as coord_mod

        original_cooldown = coord_mod.INTENT_DISPATCH_COOLDOWN_SEC
        coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = 0
        try:
            await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        finally:
            coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = original_cooldown

        assert coord.client.scenarios.history.await_count == 2
        assert coord.hass.bus.async_fire.call_count == 2
        fired_sids = {
            call.args[1]["scenario_id"] for call in coord.hass.bus.async_fire.call_args_list
        }
        assert fired_sids == {"sc-main", "sc-dacha"}
        # Cursors per home обновились.
        assert coord._last_intent_event_time["home-main"] == "2026-04-27T15:00:00Z"
        assert coord._last_intent_event_time["home-dacha"] == "2026-04-27T13:00:00Z"

    @pytest.mark.asyncio
    async def test_one_home_history_failure_does_not_block_other(self):
        """Если history по одному дому падает — другой обрабатывается.
        Pre-seed cursors чтобы issue-#35 first-push gate не глушил fire.
        """
        coord = _coord_with_homes(["home-main", "home-dacha"])
        coord._last_intent_event_time["home-main"] = "2026-04-27T00:00:00Z"
        coord._last_intent_event_time["home-dacha"] = "2026-04-27T00:00:00Z"

        def history_by_home(home_id, **kwargs):
            if home_id == "home-main":
                raise RuntimeError("boom")
            return [_event(time="2026-04-27T13:00:00Z", sid="sc-dacha")]

        coord.client.scenarios.history = AsyncMock(side_effect=history_by_home)
        msg = MagicMock()
        msg.topic = MagicMock(value="scenario_widgets")
        msg.target_device_id = None
        msg.to_dict = MagicMock(return_value={})

        from custom_components.sberhome import coordinator as coord_mod

        original_cooldown = coord_mod.INTENT_DISPATCH_COOLDOWN_SEC
        coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = 0
        try:
            await SberHomeCoordinator._on_ws_scenario_widgets(coord, msg)
        finally:
            coord_mod.INTENT_DISPATCH_COOLDOWN_SEC = original_cooldown

        # «Дача» fire'нула, «Мой дом» — нет (упал history).
        coord.hass.bus.async_fire.assert_called_once()
        fired_sid = coord.hass.bus.async_fire.call_args[0][1]["scenario_id"]
        assert fired_sid == "sc-dacha"

    @pytest.mark.asyncio
    async def test_duplicate_push_skipped_by_lock(self):
        """Sber шлёт UPDATE_WIDGETS парами ×2 за <100ms — второй вызов
        попадает на занятый lock, history.fetch вызывается ровно 1 раз
        (для всех домов). Pre-seed cursor — иначе первый push gate'ится
        issue-#35 fix'ом и history может вообще не дёрнуться (cursor=None
        retry skipped).
        """
        coord = _coord_with_home()
        coord._last_intent_event_time["home-1"] = "2026-04-27T00:00:00Z"

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
        # history дёрнулась ОДИН РАЗ (1 home × 1 не-залоченный push) —
        # второй WS push скиплен через lock.
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
