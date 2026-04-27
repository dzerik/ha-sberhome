"""ScenarioTemplatesAPI — endpoints `/gateway/v1/scenario-templates/*`.

Шаблоны сценариев — справочник «готовых» сценариев, которые
пользователь может создать одним кликом из мобильного приложения
(`«режим сна»`, `«я ушёл»` и т.п.). Семантически отдельные от
`scenario/v2/scenario` (там — пользовательские сценарии); шаблоны
read-only и сгруппированы по device/group/screen.

Endpoints:
- `GET /scenario-templates/short` — короткий список (id + name).
- `GET /scenario-templates/device` — шаблоны под one-device триггеры.
- `GET /scenario-templates/group` — шаблоны под группы устройств.
- `GET /scenario-templates/rooms` — шаблоны для комнат.
- `GET /scenario-templates/screen/` — шаблоны для главного экрана.
- `GET /scenario-templates/hide` — список скрытых templates.
"""

from __future__ import annotations

from typing import Any

from ..transport import HttpTransport


class ScenarioTemplatesAPI:
    """REST API для каталога scenario-templates (read-only)."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def list_short(self) -> list[dict[str, Any]]:
        """GET `/scenario-templates/short` — компактный список."""
        return _ensure_list(await self._fetch("/scenario-templates/short"))

    async def list_device(self) -> list[dict[str, Any]]:
        """GET `/scenario-templates/device`."""
        return _ensure_list(await self._fetch("/scenario-templates/device"))

    async def list_group(self) -> list[dict[str, Any]]:
        """GET `/scenario-templates/group`."""
        return _ensure_list(await self._fetch("/scenario-templates/group"))

    async def list_rooms(self) -> list[dict[str, Any]]:
        """GET `/scenario-templates/rooms`."""
        return _ensure_list(await self._fetch("/scenario-templates/rooms"))

    async def list_screen(self) -> list[dict[str, Any]]:
        """GET `/scenario-templates/screen/`."""
        return _ensure_list(await self._fetch("/scenario-templates/screen/"))

    async def list_hidden(self) -> list[dict[str, Any]]:
        """GET `/scenario-templates/hide`."""
        return _ensure_list(await self._fetch("/scenario-templates/hide"))

    async def _fetch(self, path: str) -> Any:
        resp = await self._transport.get(path)
        return _unwrap_result(resp.json())


# ----- helpers -----
def _unwrap_result(payload: Any) -> Any:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        return payload["result"]
    return payload


def _ensure_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("templates"), list):
        return [item for item in payload["templates"] if isinstance(item, dict)]
    return []


__all__ = ["ScenarioTemplatesAPI"]
