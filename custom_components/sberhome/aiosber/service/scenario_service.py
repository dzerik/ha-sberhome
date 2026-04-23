"""ScenarioService — управление сценариями Sber v2."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..api.scenarios import ScenarioAPI
    from ..dto.scenario import ScenarioDto


class ScenarioService:
    """High-level scenario operations."""

    def __init__(self, api: ScenarioAPI) -> None:
        self._api = api

    async def list_all(self) -> list[ScenarioDto]:
        return await self._api.list()

    async def get(self, scenario_id: str) -> ScenarioDto:
        return await self._api.get(scenario_id)

    async def delete(self, scenario_id: str) -> None:
        await self._api.delete(scenario_id)

    async def get_at_home(self) -> bool:
        return await self._api.get_at_home()

    async def set_at_home(self, value: bool) -> None:
        await self._api.set_at_home(value)


__all__ = ["ScenarioService"]
