"""IntentService — high-level CRUD над `coordinator.client.scenarios`.

WS endpoints (`websocket_api/intents.py`) делегируют сюда. Сам coordinator
не зависит от модуля intents — service инжектится снаружи.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .encoder import decode_scenario, encode_scenario
from .spec import IntentSpec

if TYPE_CHECKING:
    from ..coordinator import SberHomeCoordinator


class IntentService:
    """Operations on Sber-сценариях, представленных как IntentSpec.

    Все методы async, ошибки от Sber API (httpx errors, ApiError)
    пробрасываются — WS-endpoint их catch'ает и переводит в
    `connection.send_error`.
    """

    def __init__(self, coordinator: SberHomeCoordinator) -> None:
        self._coord = coordinator

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------
    async def list_intents(self) -> list[IntentSpec]:
        """Все сценарии Sber как IntentSpec'ы.

        Дёргает /scenario/v2/scenario, parsing в spec'ы. Кэш сценариев
        в координаторе (coordinator.scenarios) тоже обновляется
        периодически, но мы шлём свежий fetch — UI ждёт точного списка
        после CRUD-операций.
        """
        # API возвращает list[ScenarioDto] — но мы хотим raw dict для
        # forward-compat с raw_extras. Используем low-level transport.
        resp = await self._coord.home_api._transport.get("/scenario/v2/scenario")
        payload = resp.json()
        # Sber отдаёт {"scenarios": [...], "pagination": {...}} — НЕ
        # обёрнутый в "result" (live observation).
        scenarios = _extract_scenarios_list(payload)
        specs = [decode_scenario(s) for s in scenarios]
        # Заполняем last_fired_at из event log (best-effort).
        await self._populate_last_fired_at(specs)
        return specs

    async def get_intent(self, scenario_id: str) -> IntentSpec | None:
        """Один сценарий по id, или None если не найден."""
        resp = await self._coord.home_api._transport.get(f"/scenario/v2/scenario/{scenario_id}")
        payload = resp.json()
        if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
            payload = payload["result"]
        if not isinstance(payload, dict) or not payload.get("id"):
            return None
        spec = decode_scenario(payload)
        await self._populate_last_fired_at([spec])
        return spec

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------
    async def create_intent(self, spec: IntentSpec) -> IntentSpec:
        """Создать новый Sber-сценарий из IntentSpec.

        Returns:
            IntentSpec с заполненным id (из ответа Sber).
        """
        body = encode_scenario(spec)
        # Sber требует POST без id — encoder его и не выставляет (spec.id
        # игнорируется на encode).
        body.pop("id", None)
        resp = await self._coord.home_api._transport.post("/scenario/v2/scenario", json=body)
        payload = resp.json()
        if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
            payload = payload["result"]
        return decode_scenario(payload) if isinstance(payload, dict) else spec

    async def update_intent(self, scenario_id: str, spec: IntentSpec) -> IntentSpec:
        """Обновить существующий сценарий.

        IMPORTANT: spec.raw_extras должен быть actually populated decoder'ом
        (т.е. UI должен передавать spec полученный из list/get, не
        сконструированный с нуля). Иначе при update теряются image/meta/
        home_id и Sber может ответить ошибкой.
        """
        body = encode_scenario(spec)
        # Sber хочет id внутри body для PUT — encoder его не ставит,
        # но можем добавить из аргумента.
        body["id"] = scenario_id
        resp = await self._coord.home_api._transport.put(
            f"/scenario/v2/scenario/{scenario_id}", json=body
        )
        payload = resp.json()
        if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
            payload = payload["result"]
        return decode_scenario(payload) if isinstance(payload, dict) else spec

    async def delete_intent(self, scenario_id: str) -> None:
        await self._coord.home_api._transport.delete(f"/scenario/v2/scenario/{scenario_id}")

    async def test_intent(self, scenario_id: str) -> dict[str, Any]:
        """«Test now» — выполнить actions сценария one-shot.

        Sber API НЕ предоставляет programmatic-run scenario by id —
        нет endpoint'а вроде POST /scenario/v2/scenario/{id}/run.
        Сценарий запускается только своими триггерами (phrase / time /
        device-condition).

        Workaround: вытаскиваем actions из spec'а, encode'им в tasks,
        и шлём через POST /scenario/v2/command — это **создаёт одноразовый
        command** с теми же tasks. Эффект для пользователя идентичный
        (TTS произнесётся, device state поменяется), но это not-the-same
        как реальное срабатывание сценария:

        - НЕ попадает в `/scenario/v2/event` log (мы не увидим
          `sberhome_intent` HA event при тесте через UI кнопку).
        - НЕ запускает phrase-condition matching — мы выполняем
          сами actions, минуя trigger.

        Endpoint требует body shape ScenarioCommandDto (name, tasks,
        condition) — name>=1 char, condition должна быть валидной но
        может быть «никогда не срабатывающим» phrase trigger'ом.
        """
        # Получаем актуальный spec — нужен для encoded tasks.
        spec = await self.get_intent(scenario_id)
        if spec is None:
            raise ValueError(f"Intent {scenario_id} not found")

        # Encode actions в Sber-tasks через тот же encoder, что и create/update.
        from .registry import get_action

        tasks: list[dict[str, Any]] = []
        for action in spec.actions:
            if action.unknown:
                raw = action.data.get("raw")
                if isinstance(raw, dict):
                    tasks.append(raw)
                continue
            reg = get_action(action.type)
            if reg is not None:
                tasks.extend(reg.encode(action.data))

        if not tasks:
            # Нечего исполнять (ha_event_only сценарий) — просто возвращаем
            # success без side-effect'а. UI может фейк-показать что Sber
            # event fire'нулся.
            return {
                "ok": True,
                "executed_tasks": 0,
                "note": "ha_event_only — nothing to execute on Sber side",
            }

        # Body для POST /scenario/v2/command.
        # condition обязателен — используем dummy phrase которая никогда
        # не сработает (Sber хранит, но не parse'ит для one-shot command).
        # name>=1 char (Sber требует, иначе HTTP 400).
        name = (spec.name or "Test").strip() or "Test"
        body = {
            "name": f"[HA test] {name}"[:128],
            "tasks": tasks,
            "condition": {
                "type": "PHRASES",
                "phrases_data": {"phrases": ["__ha_test_never_match__"]},
            },
        }
        return await self._coord.client.scenarios.execute_command(body)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _populate_last_fired_at(self, specs: list[IntentSpec]) -> None:
        """Best-effort fill `last_fired_at` для каждого spec'а из event log.

        Берём top-N последних событий и матчим object_id == spec.id.
        Если home_id неизвестен — skip.
        """
        home = self._coord.state_cache.get_home()
        if home is None or not home.id:
            return
        if not specs:
            return
        try:
            events = await self._coord.client.scenarios.history(
                home.id, limit=max(10, len(specs) * 2)
            )
        except Exception:  # noqa: BLE001 — best-effort, без last_fired_at прожить можно
            return
        latest_per_id: dict[str, str] = {}
        for ev in events:
            if ev.object_id and ev.event_time and ev.object_id not in latest_per_id:
                latest_per_id[ev.object_id] = ev.event_time
        for spec in specs:
            if spec.id and spec.id in latest_per_id:
                spec.last_fired_at = latest_per_id[spec.id]


def _extract_scenarios_list(payload: Any) -> list[dict[str, Any]]:
    """Достать `scenarios[]` из ответа /scenario/v2/scenario."""
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        payload = payload["result"]
    if isinstance(payload, dict):
        items = payload.get("scenarios")
        if isinstance(items, list):
            return [s for s in items if isinstance(s, dict)]
    if isinstance(payload, list):
        return [s for s in payload if isinstance(s, dict)]
    return []


__all__ = ["IntentService"]
