"""IndicatorAPI — endpoints `/gateway/v1/devices/indicator/*`.

LED-индикаторы устройств (например на SberBoom): можно сменить цвет / яркость
для разных состояний (online/offline/error/notification).

Endpoints:
- `GET /devices/indicator/values` — текущие настройки + список доступных.
- `PUT /devices/indicator/values` — обновить.
"""

from __future__ import annotations

from typing import Any

from ..dto import IndicatorColor, IndicatorColorBody, IndicatorColors
from ..exceptions import ProtocolError
from ..transport import HttpTransport


class IndicatorAPI:
    """REST API for LED indicator color settings."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def get(self) -> IndicatorColors:
        """Return default + current colors как `IndicatorColors` DTO."""
        resp = await self._transport.get("/devices/indicator/values")
        payload = _unwrap_dict(resp.json())
        result = IndicatorColors.from_dict(payload)
        if result is None:
            raise ProtocolError("IndicatorColors.from_dict returned None")
        return result

    async def get_raw(self) -> dict[str, Any]:
        """То же что `get()`, но без парсинга DTO (для отладки)."""
        resp = await self._transport.get("/devices/indicator/values")
        return _unwrap_dict(resp.json())

    async def set(self, color: IndicatorColor) -> None:
        """Установить новый цвет индикатора."""
        body = IndicatorColorBody(indicator_color=color)
        await self._transport.put("/devices/indicator/values", json=body.to_dict())


# ----- helpers -----
def _unwrap_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        return payload["result"]
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"Expected dict, got {type(payload).__name__}")


__all__ = ["IndicatorAPI"]
