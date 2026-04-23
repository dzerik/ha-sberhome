"""ScenarioAPI — endpoints `/gateway/v1/scenario/v2/*`.

Сценарии Sber v2 — комбинируют trigger (event) → action (command). Похожи на
HA-automations, но живут в облаке Sber.

Endpoints (gateway/v1):
- `GET /scenario/v2/scenario` — список сценариев.
- `GET /scenario/v2/scenario/{id}` — один.
- `POST /scenario/v2/scenario` — создать.
- `PUT /scenario/v2/scenario/{id}` — обновить.
- `DELETE /scenario/v2/scenario/{id}` — удалить.
- `POST /scenario/v2/command` — отправить разовую команду (без сценария).
- `POST /scenario/v2/event` — триггер event.
- `GET /scenario/v2/widget` — виджеты.
- `GET /scenario/v2/system-scenario` — системные.
- `PUT /scenario/v2/set-requires` — требования (зависимости).
- `GET/PUT /scenario/v2/home/variable/at_home` — переменная "я дома".
- `GET /scenario/v2/scenario/form` — форма редактора.

Точная shape объекта сценария не до конца задокументирована — оставляем как
сырой dict (DTO для scenario может быть добавлен в будущем PR).
"""

from __future__ import annotations

from typing import Any

from ..dto.scenario import ScenarioDto
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

    async def fire_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Триггер события (для запуска сценариев извне)."""
        resp = await self._transport.post("/scenario/v2/event", json=event)
        return _unwrap_dict(resp.json())

    async def set_requires(self, requires: dict[str, Any]) -> None:
        await self._transport.put("/scenario/v2/set-requires", json=requires)

    # ----- "at_home" variable -----
    async def get_at_home(self) -> bool:
        """Текущее значение переменной "я дома"."""
        resp = await self._transport.get("/scenario/v2/home/variable/at_home")
        payload = _unwrap_dict(resp.json())
        return bool(payload.get("at_home", False))

    async def set_at_home(self, at_home: bool) -> None:
        await self._transport.put(
            "/scenario/v2/home/variable/at_home",
            json={"at_home": at_home},
        )

    async def get_form(self) -> dict[str, Any]:
        """Форма UI-конструктора сценариев."""
        resp = await self._transport.get("/scenario/v2/scenario/form")
        return _unwrap_dict(resp.json())


# ----- helpers -----
def _unwrap_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        return payload["result"]
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"Expected dict, got {type(payload).__name__}")


def _unwrap_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        payload = payload["result"]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Expected list, got {type(payload).__name__}")


__all__ = ["ScenarioAPI"]
