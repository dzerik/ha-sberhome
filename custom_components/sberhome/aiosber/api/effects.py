"""LightEffectsAPI — endpoints `/gateway/v1/light/effects`.

Каталог пресетов эффектов для led_strip / RGB-ламп. Используется
HA-слоем как источник `effect_list` для `light` платформы и для
команды `light.turn_on(effect=...)`.

Endpoints:
- `GET /light/effects` — список всех эффектов: `{"id", "name",
  "preview", "category"}`. Эффекты категоризованы (`mood`, `party`,
  `nature` и т.п.) — пригодится для группировки в UI.
"""

from __future__ import annotations

from typing import Any

from ..transport import HttpTransport


class LightEffectsAPI:
    """REST API для каталога световых эффектов."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def list(self) -> list[dict[str, Any]]:
        """GET `/light/effects` — все доступные эффекты.

        Returns:
            list of dict с полями `id`, `name`, опционально
            `preview` (URL картинки), `category` (slug группировки).
            Пустой list, если каталог не возвращён.
        """
        resp = await self._transport.get("/light/effects")
        payload = _unwrap_result(resp.json())
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("effects"), list):
            return payload["effects"]
        return []


# ----- helpers -----
def _unwrap_result(payload: Any) -> Any:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        return payload["result"]
    return payload


__all__ = ["LightEffectsAPI"]
