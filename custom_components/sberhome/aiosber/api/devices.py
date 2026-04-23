"""DeviceAPI — endpoints for `gateway/v1/devices/*` and device tree.

Семантика endpoints определена наблюдениями за живым REST/WS API:

- `GET /device_groups/tree` — корневой endpoint для получения **всех**
  устройств. Ответ имеет shape `{"result": {"devices": [...], "children": [...]}}`,
  где children — рекурсивная иерархия групп. Плоский dict собирается
  через `flatten_device_tree()`.
- `GET /devices/` — альтернативный endpoint, возвращает плоский список,
  но без иерархической структуры групп.
- `PUT /devices/{id}/state` — отправить команду. Body: `desired_state` массив
  + `device_id` + UTC `timestamp` (Sber требует все три поля).
- `GET /devices/enums` — справочники enum-значений атрибутов.
- `PUT /devices/{id}/name` — переименовать.
- `PUT /devices/{id}/parent` — перенести в группу (или из группы).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..dto import (
    AttributeValueDto,
    DesiredDeviceStateDto,
    DeviceDto,
    UpdateNameBody,
    UpdateParentBody,
)
from ..exceptions import ProtocolError
from ..transport import HttpTransport


class DeviceAPI:
    """REST API for Sber smart home devices.

    Args:
        transport: pre-configured `HttpTransport` (DI). Не владеет им —
            не закрывает в `aclose()`.
    """

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    # ----- list / get -----
    async def list(self) -> list[DeviceDto]:
        """Return all devices, traversing the group tree.

        Использует `device_groups/tree` — единственный надёжный способ
        получить все устройства независимо от структуры групп.
        """
        resp = await self._transport.get("/device_groups/tree")
        payload = _unwrap_result(resp.json())
        return [_to_device(d) for d in flatten_device_tree(payload)]

    async def list_flat(self) -> list[DeviceDto]:
        """Alternative: GET /devices/ (без иерархии групп)."""
        resp = await self._transport.get("/devices/")
        payload = _unwrap_result(resp.json())
        if not isinstance(payload, list):
            raise ProtocolError(f"Expected list from /devices/, got {type(payload).__name__}")
        return [_to_device(d) for d in payload]

    async def get(self, device_id: str) -> DeviceDto:
        """Return single device. Raises `ApiError` (404) if not found."""
        resp = await self._transport.get(f"/devices/{device_id}")
        payload = _unwrap_result(resp.json())
        if not isinstance(payload, dict):
            raise ProtocolError(
                f"Expected dict from /devices/{device_id}, got {type(payload).__name__}"
            )
        return _to_device(payload)

    # ----- mutations -----
    async def set_state(
        self,
        device_id: str,
        attributes: list[AttributeValueDto],
        *,
        timestamp: str | None = None,
    ) -> None:
        """Send command to a device.

        Args:
            device_id: device UUID.
            attributes: список AttributeValueDto для desired_state.
            timestamp: UTC ISO-8601 (default: текущее время).
                Используется формат `YYYY-MM-DDTHH:MM:SS.sssZ` (с Z, не +00:00).
        """
        ts = timestamp or _utc_iso_z()
        body = {
            "device_id": device_id,
            "desired_state": [a.to_dict() for a in attributes],
            "timestamp": ts,
        }
        await self._transport.put(f"/devices/{device_id}/state", json=body)

    async def set_state_dto(
        self,
        device_id: str,
        body: DesiredDeviceStateDto,
        *,
        timestamp: str | None = None,
    ) -> None:
        """Same as `set_state()`, но принимает готовый DesiredDeviceStateDto."""
        await self.set_state(device_id, body.desired_state, timestamp=timestamp)

    async def rename(self, device_id: str, name: str) -> None:
        await self._transport.put(
            f"/devices/{device_id}/name",
            json=UpdateNameBody(name=name).to_dict(),
        )

    async def move(self, device_id: str, parent_id: str | None) -> None:
        """Перенести устройство в группу (или вынести: parent_id=None)."""
        await self._transport.put(
            f"/devices/{device_id}/parent",
            json=UpdateParentBody(parent_id=parent_id).to_dict(),
        )

    # ----- meta -----
    async def enums(self) -> dict[str, Any]:
        """GET /devices/enums — справочники enum-значений атрибутов."""
        resp = await self._transport.get("/devices/enums")
        return _unwrap_result(resp.json())

    async def discover(self, device_id: str) -> dict[str, Any]:
        """GET /devices/{id}/discovery — discovery info (для bridges/hubs)."""
        resp = await self._transport.get(f"/devices/{device_id}/discovery")
        return _unwrap_result(resp.json())


# =============================================================================
# Helpers
# =============================================================================
def flatten_device_tree(tree: dict[str, Any]) -> list[dict[str, Any]]:
    """Recursively flatten {"devices": [...], "children": [...]} в плоский list.

    Используется для парсинга ответа `device_groups/tree`.
    """
    devices: list[dict[str, Any]] = list(tree.get("devices") or [])
    for child in tree.get("children") or []:
        devices.extend(flatten_device_tree(child))
    return devices


def _unwrap_result(payload: Any) -> Any:
    """Развернуть `{"result": ...}` обёртку, если она есть.

    Sber Gateway оборачивает большинство успешных ответов в `{"result": ...}`.
    Старые endpoints (или non-result ответы) — возвращаются как есть.
    """
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        # Обычно: {"result": ..., "code": 0} или просто {"result": ...}
        return payload["result"]
    return payload


def _to_device(data: dict[str, Any]) -> DeviceDto:
    """Парсить dict → DeviceDto, гарантируя non-None результат."""
    device = DeviceDto.from_dict(data)
    if device is None:
        raise ProtocolError("DeviceDto.from_dict returned None")
    return device


def _utc_iso_z() -> str:
    """Текущее время как `YYYY-MM-DDTHH:MM:SS.sssZ` (с Z).

    Sber API отказывается от формата `+00:00` — нужен буквально 'Z'.
    """
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


# Re-export for convenience
__all__ = ["DeviceAPI", "flatten_device_tree"]
