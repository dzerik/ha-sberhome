"""GroupService — управление группами/комнатами."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dto import AttributeValueDto

if TYPE_CHECKING:
    from ..api.groups import GroupAPI
    from ..dto.device import DeviceDto
    from ..dto.union import UnionDto, UnionTreeDto
    from .state_cache import StateCache


class GroupService:
    """High-level group/room operations backed by StateCache."""

    def __init__(self, api: GroupAPI, cache: StateCache) -> None:
        self._api = api
        self._cache = cache

    # ------------------------------------------------------------------
    # Queries (from cache)
    # ------------------------------------------------------------------
    def get(self, group_id: str) -> UnionDto | None:
        return self._cache.get_group(group_id)

    def list_all(self) -> list[UnionDto]:
        return list(self._cache.get_all_groups().values())

    def list_rooms(self) -> list[UnionDto]:
        return self._cache.get_rooms()

    def get_home(self) -> UnionDto | None:
        return self._cache.get_home()

    def get_tree(self) -> UnionTreeDto | None:
        return self._cache.get_tree()

    def devices_in_group(self, group_id: str) -> list[DeviceDto]:
        """Все устройства, принадлежащие группе."""
        group = self._cache.get_group(group_id)
        if group is None or not group.device_ids:
            return []
        return [d for did in group.device_ids if (d := self._cache.get_device(did)) is not None]

    def room_for_device(self, device_id: str) -> str | None:
        """Имя комнаты для устройства."""
        return self._cache.device_room(device_id)

    # ------------------------------------------------------------------
    # Commands (HTTP)
    # ------------------------------------------------------------------
    async def set_state(
        self,
        group_id: str,
        attrs: list[AttributeValueDto],
    ) -> None:
        """Команда на всю группу (все устройства)."""
        await self._api.set_state(group_id, attrs)

    async def create(self, name: str, *, parent_id: str | None = None) -> UnionDto:
        """Создать группу. Возвращает созданную."""
        from ..dto.union import UnionDto

        raw = await self._api._transport.post(
            "/device_groups/",
            json={"name": name, **({"parent_id": parent_id} if parent_id else {})},
        )
        payload = raw.json()
        if isinstance(payload, dict) and "result" in payload:
            payload = payload["result"]
        dto = UnionDto.from_dict(payload)
        if dto is None:
            from ..exceptions import ProtocolError

            raise ProtocolError("Cannot parse created group")
        return dto

    async def delete(self, group_id: str) -> None:
        await self._api.delete(group_id)

    async def rename(self, group_id: str, name: str) -> None:
        await self._api.rename(group_id, name)


__all__ = ["GroupService"]
