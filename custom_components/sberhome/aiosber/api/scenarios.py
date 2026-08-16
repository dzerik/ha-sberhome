"""ScenarioAPI — endpoints `/gateway/v1/scenario/v2/*`.

Сценарии Sber v2 — комбинируют trigger (event) → action (command). Похожи на
HA-automations, но живут в облаке Sber.

Endpoints (gateway/v1):
- `GET /scenario/v2/scenario` — список сценариев.
- `GET /scenario/v2/scenario/{id}` — один.
- `POST /scenario/v2/scenario` — создать.
- `PUT /scenario/v2/scenario/{id}` — обновить.
- `DELETE /scenario/v2/scenario/{id}` — удалить.
- `POST /scenario/v2/scenario/{id}/run` — запустить сейчас.
- `POST /scenario/v2/scenario/{id}/stop` — остановить исполняющийся.
- `POST /scenario/v2/scenario/{id}/cancel` — отменить.
- `PATCH /scenario/v2/scenario/{id}/active` — тумблер автосрабатывания.
- `POST /scenario/v2/command` — отправить разовую команду (без сценария).
- `POST /scenario/v2/event` — триггер event.
- `GET /scenario/v2/widget` — виджеты.
- `GET /scenario/v2/system-scenario` — системные.
- `POST /scenario/v2/scenario/set-requires` — условие «дома/не дома».
- `GET/PUT /scenario/v2/home/variable/at_home` — переменная "я дома".
- `GET /scenario/v2/scenario/form` — форма редактора.

Точная shape объекта сценария не до конца задокументирована — оставляем как
сырой dict (DTO для scenario может быть добавлен в будущем PR).
"""

from __future__ import annotations

from typing import Any

from ..dto.scenario import ScenarioDto, ScenarioEventDto
from ..transport import HttpTransport


class ScenarioAPI:
    """REST API for Sber scenarios v2."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    # ----- list / get -----
    async def list(self) -> list[ScenarioDto]:
        resp = await self._transport.get("/scenario/v2/scenario")
        raw = _unwrap_list(resp.json())
        return [s for d in raw if (s := ScenarioDto.from_dict(d)) is not None]

    async def list_raw(self) -> list[dict[str, Any]]:
        """Raw list — bypasses DTO conversion.

        Используется в диагностике / при исследовании wire-формата:
        DTO теряет вложенные поля (`steps[]`, `tasks[]`, `pronounce_data`),
        а сырой dict сохраняет всё что отдал Sber.
        """
        resp = await self._transport.get("/scenario/v2/scenario")
        return _unwrap_list(resp.json())

    async def get(self, scenario_id: str) -> ScenarioDto:
        resp = await self._transport.get(f"/scenario/v2/scenario/{scenario_id}")
        raw = _unwrap_dict(resp.json())
        dto = ScenarioDto.from_dict(raw)
        if dto is None:
            from ..exceptions import ProtocolError

            raise ProtocolError(f"Cannot parse scenario {scenario_id}")
        return dto

    async def list_system(self) -> list[dict[str, Any]]:
        """Системные сценарии (предустановленные Sber)."""
        resp = await self._transport.get("/scenario/v2/system-scenario")
        return _unwrap_list(resp.json())

    async def list_widgets(self) -> list[dict[str, Any]]:
        resp = await self._transport.get("/scenario/v2/widget")
        return _unwrap_list(resp.json())

    # ----- mutations -----
    async def create(self, scenario: dict[str, Any]) -> dict[str, Any]:
        resp = await self._transport.post("/scenario/v2/scenario", json=scenario)
        return _unwrap_dict(resp.json())

    async def update(self, scenario_id: str, scenario: dict[str, Any]) -> dict[str, Any]:
        resp = await self._transport.put(
            f"/scenario/v2/scenario/{scenario_id}",
            json=scenario,
        )
        return _unwrap_dict(resp.json())

    async def delete(self, scenario_id: str) -> None:
        await self._transport.delete(f"/scenario/v2/scenario/{scenario_id}")

    async def execute_command(self, command: dict[str, Any]) -> dict[str, Any]:
        """Разовая команда без сохранения как сценарий."""
        resp = await self._transport.post("/scenario/v2/command", json=command)
        return _unwrap_dict(resp.json())

    async def run(self, scenario_id: str) -> dict[str, Any]:
        """`POST /scenario/v2/scenario/{id}/run` — запустить сценарий программно.

        То же что кнопка «Запустить действие» в мобильном приложении Sber.
        Тело — `{is_active: true}` (одно опциональное поле).

        Используется HA-side для test_intent — реально выполнить Sber
        actions (TTS / device_command / etc.) без необходимости
        произносить фразу в колонку.
        """
        resp = await self._transport.post(
            f"/scenario/v2/scenario/{scenario_id}/run",
            json={"is_active": True},
        )
        # Ответ может быть пустым {} либо ResultDto-обёрнутым.
        try:
            return _unwrap_dict(resp.json())
        except (ValueError, AttributeError):
            return {"ok": True}

    async def stop(self, scenario_id: str) -> None:
        """`POST /scenario/v2/scenario/{id}/stop` — остановить исполняющийся сценарий.

        Тело запроса — пустой объект `{}`. Симметрично `run` — прерывает
        уже запущенный (в т.ч. режимный/длящийся) сценарий.
        """
        await self._transport.post(
            f"/scenario/v2/scenario/{scenario_id}/stop",
            json={},
        )

    async def cancel(self, scenario_id: str) -> None:
        """`POST /scenario/v2/scenario/{id}/cancel` — отменить запланированный/идущий сценарий.

        Тело — `{is_active: true}` (как у `run`, id в path).
        """
        await self._transport.post(
            f"/scenario/v2/scenario/{scenario_id}/cancel",
            json={"is_active": True},
        )

    async def set_active(self, scenario_id: str, active: bool) -> None:
        """`PATCH /scenario/v2/scenario/{id}/active` — тумблер активности сценария.

        Включает/выключает автосрабатывание сценария (НЕ запуск сейчас).
        Тело — `{is_active: <bool>}`; метод именно PATCH, не POST.
        """
        await self._transport.patch(
            f"/scenario/v2/scenario/{scenario_id}/active",
            json={"is_active": active},
        )

    async def fire_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Триггер события (для запуска сценариев извне)."""
        resp = await self._transport.post("/scenario/v2/event", json=event)
        return _unwrap_dict(resp.json())

    async def set_requires(self, requires: dict[str, Any]) -> None:
        """`POST /scenario/v2/scenario/set-requires` — условие «дома/не дома» сценария.

        Тело — `ScenarioRequiresDto{scenario_id, requires}`. Это НЕ
        `PUT /scenario/v2/set-requires` (устаревший путь давал 404).
        """
        await self._transport.post("/scenario/v2/scenario/set-requires", json=requires)

    # ----- "at_home" variable -----
    async def get_at_home(self, home_id: str | None = None) -> bool:
        """Текущее значение переменной "я дома".

        Ответ — вложенный `{"variable": {"name": "at_home", "value":
        {"bool_value": true}}}`. Парсим устойчиво: поддерживаем и вложенную
        форму, и плоскую (`{"at_home": bool}` / `{"bool_value": bool}`) на
        случай server-side drift'а.
        """
        params = {"home_id": home_id} if home_id else None
        resp = await self._transport.get(
            "/scenario/v2/home/variable/at_home",
            params=params,
        )
        return _extract_at_home(_unwrap_dict(resp.json()))

    async def set_at_home(self, at_home: bool, home_id: str | None = None) -> None:
        """Записать переменную "я дома".

        Тело — исторически рабочее одноключевое `{"at_home": bool}`
        (проверено в проде). Не добавляем лишних ключей: строгий шлюз
        может отвергнуть запрос с неизвестным полем целиком. Опциональный
        `home_id` уходит в query.
        """
        params = {"home_id": home_id} if home_id else None
        await self._transport.put(
            "/scenario/v2/home/variable/at_home",
            params=params,
            json={"at_home": at_home},
        )

    async def get_form(self) -> dict[str, Any]:
        """Форма UI-конструктора сценариев."""
        resp = await self._transport.get("/scenario/v2/scenario/form")
        return _unwrap_dict(resp.json())

    # ----- history (event log) -----
    async def history(
        self,
        home_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ScenarioEventDto]:
        """`GET /scenario/v2/event` — журнал срабатываний сценариев.

        Используется HA-coordinator'ом для catch'а голосовых команд:
        при `scenario_widgets.UPDATE_WIDGETS` push'е через WS — делается
        запрос с `offset=0&limit=N`, новые события (по `event_time`)
        конвертируются в `sberhome_intent` HA event'ы.

        Args:
            home_id: id Sber-дома (см. координатор `home_id` discovery).
            offset / limit: пагинация (limit≤200 эмпирически).

        Returns:
            Список `ScenarioEventDto`, отсортированный сервером по
            `event_time desc` (свежие сначала).
        """
        params = {
            "home_id": home_id,
            "pagination.offset": str(offset),
            "pagination.limit": str(limit),
        }
        resp = await self._transport.get("/scenario/v2/event", params=params)
        payload = resp.json()
        # Sber возвращает {"events": [...], "pagination": {...}} — НЕ
        # обёрнуто в "result" (см. live response). Поддержим оба варианта
        # на случай drift'а.
        events = _extract_events(payload)
        return [dto for raw in events if (dto := ScenarioEventDto.from_dict(raw)) is not None]


# ----- helpers -----
def _extract_at_home(payload: dict[str, Any]) -> bool:
    """Достать значение at_home из ответа /home/variable/at_home.

    Поддерживает три формы:
    - вложенную ``{"variable": {"value": {"bool_value": true}}}`` (реальный wire);
    - полу-вложенную ``{"value": {"bool_value": true}}``;
    - плоскую ``{"at_home": true}`` / ``{"bool_value": true}``.
    """
    node: Any = payload.get("variable", payload)
    if isinstance(node, dict):
        value = node.get("value", node)
        if isinstance(value, dict):
            if "bool_value" in value:
                return bool(value["bool_value"])
            if "at_home" in value:
                return bool(value["at_home"])
    for key in ("bool_value", "at_home"):
        if key in payload:
            return bool(payload[key])
    return False


def _unwrap_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        return payload["result"]
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"Expected dict, got {type(payload).__name__}")


def _unwrap_list(payload: Any) -> list[dict[str, Any]]:
    """Достать список из Sber API response.

    Принимает:
    - Plain list ``[...]``.
    - Обёрнутый ``{"result": [...]}`` (sometimes with siblings вроде
      ``pagination`` — Sber drift'ит, см. ``/scenario/v2/event``).
    - Dict с единственным list-valued key (например ``{"scenarios": [...]}``).
    """
    if isinstance(payload, dict):
        result = payload.get("result")
        if isinstance(result, list):
            return result
        list_values = [v for v in payload.values() if isinstance(v, list)]
        if len(list_values) == 1:
            return list_values[0]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Expected list, got {type(payload).__name__}")


def _extract_events(payload: Any) -> list[dict[str, Any]]:
    """Достать `events[]` из ответа /scenario/v2/event.

    Sber возвращает goly `{"events": [...], "pagination": {...}}` без
    `result`-обёртки (live observation). На случай server-side drift'а
    поддерживаем и обёрнутый вариант.
    """
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        payload = payload["result"]
    if isinstance(payload, dict):
        events = payload.get("events")
        if isinstance(events, list):
            return [e for e in events if isinstance(e, dict)]
    return []


__all__ = ["ScenarioAPI"]
