"""DeviceService — высокоуровневые операции с устройствами.

Queries работают из кеша (без HTTP). Commands отправляют HTTP + optimistic
patch кеша.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..dto import AttributeValueDto, AttrKey

if TYPE_CHECKING:
    from ..api.devices import DeviceAPI
    from ..dto.device import DeviceDto
    from .state_cache import StateCache


class DeviceService:
    """High-level device operations backed by StateCache."""

    def __init__(self, api: DeviceAPI, cache: StateCache) -> None:
        self._api = api
        self._cache = cache

    # ------------------------------------------------------------------
    # Queries (from cache, no HTTP)
    # ------------------------------------------------------------------
    def get(self, device_id: str) -> DeviceDto | None:
        return self._cache.get_device(device_id)

    def list_all(self) -> list[DeviceDto]:
        return list(self._cache.get_all_devices().values())

    def list_by_room(self, room_name: str) -> list[DeviceDto]:
        """Все устройства в указанной комнате."""
        result: list[DeviceDto] = []
        for device_id, dto in self._cache.get_all_devices().items():
            if self._cache.device_room(device_id) == room_name:
                result.append(dto)
        return result

    def list_by_category(self, category: str) -> list[DeviceDto]:
        """Все устройства с данным image_set_type (category)."""
        return [
            d for d in self._cache.get_all_devices().values()
            if d.image_set_type and category in d.image_set_type
        ]

    def has_feature(self, device_id: str, key: str) -> bool:
        """Проверить, есть ли атрибут в reported_state устройства."""
        dto = self._cache.get_device(device_id)
        if dto is None:
            return False
        return any(av.key == key for av in dto.reported_state)

    # ------------------------------------------------------------------
    # Commands (HTTP + optimistic cache update)
    # ------------------------------------------------------------------
    async def set_state(
        self,
        device_id: str,
        attrs: list[AttributeValueDto],
    ) -> None:
        """Послать команду устройству + optimistic patch кеша."""
        await self._api.set_state(device_id, attrs)
        self._cache.patch_device_desired(device_id, attrs)

    async def turn_on(self, device_id: str) -> None:
        await self.set_state(
            device_id, [AttributeValueDto.of_bool(AttrKey.ON_OFF, True)]
        )

    async def turn_off(self, device_id: str) -> None:
        await self.set_state(
            device_id, [AttributeValueDto.of_bool(AttrKey.ON_OFF, False)]
        )

    async def set_brightness(self, device_id: str, value: int) -> None:
        await self.set_state(
            device_id,
            [AttributeValueDto.of_int(AttrKey.LIGHT_BRIGHTNESS, value)],
        )

    # ------------------------------------------------------------------
    # Lifecycle / management
    # ------------------------------------------------------------------
    async def refresh(self) -> None:
        """Full refresh: GET tree → parse → cache.update_from_tree().

        Обновляет И devices И groups в одном запросе.
        """
        from ..dto.union import UnionTreeDto

        # Используем GroupAPI.tree() для typed parse
        # Но DeviceAPI тоже ходит в тот же endpoint — используем его transport
        resp = await self._api._transport.get("/device_groups/tree")
        payload = resp.json()
        if isinstance(payload, dict) and "result" in payload:
            payload = payload["result"]
        tree = UnionTreeDto.from_dict(payload)
        if tree is not None:
            self._cache.update_from_tree(tree)

    async def rename(self, device_id: str, name: str) -> None:
        await self._api.rename(device_id, name)

    async def move_to_group(
        self, device_id: str, group_id: str | None
    ) -> None:
        await self._api.move(device_id, group_id)


__all__ = ["DeviceService"]
