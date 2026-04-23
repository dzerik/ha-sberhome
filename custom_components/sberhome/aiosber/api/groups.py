"""GroupAPI — endpoints `/gateway/v1/device_groups/*`.

Группы устройств в Sber — иерархические (комнаты, "сцены"). Команда на группу
применяется ко всем устройствам в ней (с поддержкой `desired_state`).

Endpoints:
- `GET /device_groups/` — список групп.
- `GET /device_groups/tree` — иерархия групп с устройствами (используется
  `DeviceAPI.list()`).
- `GET /device_groups/{id}` — одна группа.
- `POST /device_groups/` — создать группу.
- `DELETE /device_groups/{id}` — удалить.
- `PUT /device_groups/{id}/state` — команда на группу (DesiredGroupStateDto).
- `PUT /device_groups/{id}/name` — переименовать.
- `PUT /device_groups/{id}/parent` — перенести.
- `PUT /device_groups/{id}/image` — иконка.
- `PUT /device_groups/{id}/light` — настройки освещения сцены.
- `PUT /device_groups/{id}/silent` — silent mode.
- `PUT /device_groups/order` — переупорядочить.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from ..dto import (
    AttributeValueDto,
    DesiredGroupStateDto,
    UpdateNameBody,
    UpdateParentBody,
)
from ..dto.union import UnionDto, UnionTreeDto
from ..transport import HttpTransport


class GroupAPI:
    """REST API for device groups."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    # ----- list / get -----
    async def list(self) -> list[UnionDto]:
        """Return all groups (без вложенных устройств)."""
        resp = await self._transport.get("/device_groups/")
        raw = _unwrap_list(resp.json())
        return [u for d in raw if (u := UnionDto.from_dict(d)) is not None]

    async def list_raw(self) -> list[dict[str, Any]]:
        """Return all groups as raw dicts (backward compat)."""
        resp = await self._transport.get("/device_groups/")
        return _unwrap_list(resp.json())

    async def get(self, group_id: str) -> UnionDto:
        """Return single group."""
        resp = await self._transport.get(f"/device_groups/{group_id}")
        raw = _unwrap_dict(resp.json())
        dto = UnionDto.from_dict(raw)
        if dto is None:
            from ..exceptions import ProtocolError

            raise ProtocolError(f"Cannot parse group {group_id}")
        return dto

    async def tree(self) -> UnionTreeDto:
        """Return full group tree with devices."""
        resp = await self._transport.get("/device_groups/tree")
        payload = resp.json()
        if isinstance(payload, dict) and "result" in payload:
            payload = payload["result"]
        dto = UnionTreeDto.from_dict(payload)
        if dto is None:
            from ..exceptions import ProtocolError

            raise ProtocolError("Cannot parse group tree")
        return dto

    async def tree_raw(self) -> dict[str, Any]:
        """Return full group tree as raw dict (backward compat)."""
        resp = await self._transport.get("/device_groups/tree")
        payload = resp.json()
        if isinstance(payload, dict) and "result" in payload:
            return payload["result"]
        return payload

    # ----- mutations -----
    async def create(self, name: str, *, parent_id: str | None = None) -> dict[str, Any]:
        """Создать группу. Возвращает созданную (с её id)."""
        body: dict[str, Any] = {"name": name}
        if parent_id is not None:
            body["parent_id"] = parent_id
        resp = await self._transport.post("/device_groups/", json=body)
        return _unwrap_dict(resp.json())

    async def delete(self, group_id: str) -> None:
        """Удалить группу. Устройства внутри переносятся в parent."""
        await self._transport.delete(f"/device_groups/{group_id}")

    async def set_state(
        self,
        group_id: str,
        attributes: list[AttributeValueDto],
        *,
        return_group_status: bool | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any] | None:
        """Послать команду всем устройствам группы.

        Args:
            return_group_status: если True — ответ содержит agg-статус группы.
            timestamp: см. `DeviceAPI.set_state`.
        """
        body_obj = DesiredGroupStateDto(
            desired_state=attributes,
            return_group_status=return_group_status,
        )
        body = body_obj.to_dict()
        body["timestamp"] = timestamp or _utc_iso_z()
        resp = await self._transport.put(
            f"/device_groups/{group_id}/state",
            json=body,
        )
        try:
            return _unwrap_dict(resp.json())
        except ValueError:
            return None

    async def rename(self, group_id: str, name: str) -> None:
        await self._transport.put(
            f"/device_groups/{group_id}/name",
            json=UpdateNameBody(name=name).to_dict(),
        )

    async def move(self, group_id: str, parent_id: str | None) -> None:
        await self._transport.put(
            f"/device_groups/{group_id}/parent",
            json=UpdateParentBody(parent_id=parent_id).to_dict(),
        )

    async def set_image(self, group_id: str, image_id: str) -> None:
        await self._transport.put(
            f"/device_groups/{group_id}/image",
            json={"image_id": image_id},
        )

    async def set_silent(self, group_id: str, silent: bool) -> None:
        """Silent mode — отключить уведомления / звуки группы."""
        await self._transport.put(
            f"/device_groups/{group_id}/silent",
            json={"silent": silent},
        )


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


def _utc_iso_z() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = ["GroupAPI"]
