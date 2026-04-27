"""InventoryAPI — endpoints `/gateway/v1/inventory/*`.

Информация о доступных обновлениях прошивки (OTA) для устройств,
inventory-токенах и одноразовых кодах. Используется HA-слоем для
показа `update`-entity per-device, когда у устройства появилось
обновление.

Endpoints:
- `GET /inventory/ota-upgrades` — словарь `device_id → upgrade_info`,
  где upgrade_info содержит `available_version`, `release_notes`,
  `severity`, `auto_install_at` (если запланировано) и т.п.
- `GET /inventory/tokens` — служебные токены (для pairing/binding).
- `GET /inventory/otp` — одноразовые коды для авторизации связки
  партнёрских аккаунтов.

Wire-формат восстановлен по наблюдению за обменом client ↔ Sber
Gateway. На момент написания все три endpoint'а возвращают
`{"result": ...}`-обёртку, как и остальные `/gateway/v1/*`.
"""

from __future__ import annotations

from typing import Any

from ..transport import HttpTransport


class InventoryAPI:
    """REST API для inventory-метаданных устройств.

    Args:
        transport: pre-configured `HttpTransport` (DI). Не владеет им —
            не закрывает в `aclose()`.
    """

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def list_ota_upgrades(self) -> dict[str, Any]:
        """GET `/inventory/ota-upgrades` — список доступных OTA-обновлений.

        Returns:
            dict с ключами по device_id; каждое значение содержит хотя бы
            одно из полей: `available_version`, `current_version`,
            `release_notes`, `severity`, `download_size`. Пустой словарь
            если обновлений нет ни для одного устройства.
        """
        resp = await self._transport.get("/inventory/ota-upgrades")
        return _unwrap_result(resp.json())

    async def list_tokens(self) -> dict[str, Any]:
        """GET `/inventory/tokens` — служебные токены (pairing/binding)."""
        resp = await self._transport.get("/inventory/tokens")
        return _unwrap_result(resp.json())

    async def get_otp(self) -> dict[str, Any]:
        """GET `/inventory/otp` — одноразовый код авторизации.

        Используется при привязке партнёрских аккаунтов (Tuya, intercom).
        """
        resp = await self._transport.get("/inventory/otp")
        return _unwrap_result(resp.json())


# ----- helpers -----
def _unwrap_result(payload: Any) -> dict[str, Any]:
    """Развернуть `{"result": ...}` обёртку и гарантировать dict."""
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        inner = payload["result"]
        return inner if isinstance(inner, dict) else {}
    return payload if isinstance(payload, dict) else {}


__all__ = ["InventoryAPI"]
