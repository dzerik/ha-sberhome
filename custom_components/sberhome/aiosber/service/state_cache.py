"""StateCache — typed in-memory state store.

Single source of truth для состояния всех устройств и групп.
Заменяет raw dict cache. WS-patch обновляет DTO напрямую.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..dto.device import DeviceDto
    from ..dto.union import UnionDto, UnionTreeDto
    from ..dto.values import AttributeValueDto

_LOGGER = logging.getLogger(__name__)


class StateCache:
    """Typed in-memory device/group state store.

    Thread-safety: designed for single-threaded async usage (one event loop).
    All mutations happen from coordinator callbacks — no locks needed.
    """

    def __init__(self) -> None:
        self._devices: dict[str, DeviceDto] = {}
        self._groups: dict[str, UnionDto] = {}
        self._tree: UnionTreeDto | None = None
        # Derived mappings (rebuilt on update_from_tree)
        self._device_to_room_name: dict[str, str] = {}
        self._device_to_room_id: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Read — devices
    # ------------------------------------------------------------------
    def get_device(self, device_id: str) -> DeviceDto | None:
        return self._devices.get(device_id)

    def get_all_devices(self) -> dict[str, DeviceDto]:
        return dict(self._devices)

    def device_ids(self) -> frozenset[str]:
        return frozenset(self._devices)

    # ------------------------------------------------------------------
    # Read — groups
    # ------------------------------------------------------------------
    def get_group(self, group_id: str) -> UnionDto | None:
        return self._groups.get(group_id)

    def get_all_groups(self) -> dict[str, UnionDto]:
        return dict(self._groups)

    def get_rooms(self) -> list[UnionDto]:
        """Все группы с type==ROOM."""
        from ..dto.union import UnionType

        return [
            g for g in self._groups.values()
            if g.group_type is UnionType.ROOM
        ]

    def get_home(self) -> UnionDto | None:
        """Группа с type==HOME (обычно одна)."""
        from ..dto.union import UnionType

        for g in self._groups.values():
            if g.group_type is UnionType.HOME:
                return g
        return None

    def get_tree(self) -> UnionTreeDto | None:
        return self._tree

    # ------------------------------------------------------------------
    # Read — device↔room mapping
    # ------------------------------------------------------------------
    def device_room(self, device_id: str) -> str | None:
        """Имя комнаты для устройства (или None)."""
        return self._device_to_room_name.get(device_id)

    def device_room_id(self, device_id: str) -> str | None:
        """ID комнаты для устройства (или None)."""
        return self._device_to_room_id.get(device_id)

    # ------------------------------------------------------------------
    # Write — full refresh from tree
    # ------------------------------------------------------------------
    def update_from_tree(self, tree: UnionTreeDto) -> None:
        """Parse tree → populate devices, groups, room mappings.

        Вызывается после каждого polling refresh.
        """
        self._tree = tree
        devices: dict[str, DeviceDto] = {}
        groups: dict[str, UnionDto] = {}
        device_to_room_name: dict[str, str] = {}
        device_to_room_id: dict[str, str] = {}

        self._walk_tree(
            tree, devices, groups, device_to_room_name, device_to_room_id
        )

        self._devices = devices
        self._groups = groups
        self._device_to_room_name = device_to_room_name
        self._device_to_room_id = device_to_room_id

        _LOGGER.debug(
            "StateCache updated: %d devices, %d groups, %d room mappings",
            len(devices),
            len(groups),
            len(device_to_room_name),
        )

    def _walk_tree(
        self,
        node: UnionTreeDto,
        devices: dict[str, DeviceDto],
        groups: dict[str, UnionDto],
        device_to_room_name: dict[str, str],
        device_to_room_id: dict[str, str],
    ) -> None:
        """Рекурсивно обойти дерево, собирая devices и groups."""
        from ..dto.union import UnionType

        union = node.union
        if union is not None and union.id:
            groups[union.id] = union

        # Определяем: этот node — комната?
        is_room = (
            union is not None
            and union.group_type is UnionType.ROOM
            and union.name
        )

        for device in node.devices:
            if device.id:
                devices[device.id] = device
                if is_room and union is not None:
                    device_to_room_name[device.id] = union.name  # type: ignore[arg-type]
                    device_to_room_id[device.id] = union.id  # type: ignore[arg-type]

        for child in node.children:
            self._walk_tree(
                child, devices, groups, device_to_room_name, device_to_room_id
            )

    # ------------------------------------------------------------------
    # Write — WS patch (точечное обновление)
    # ------------------------------------------------------------------
    def patch_device_state(
        self,
        device_id: str,
        reported: list[AttributeValueDto],
    ) -> DeviceDto | None:
        """WS DEVICE_STATE → точечный patch reported_state в DTO.

        Возвращает обновлённый DeviceDto или None если device не в кеше.
        """
        old = self._devices.get(device_id)
        if old is None:
            return None
        by_key = {av.key: av for av in old.reported_state}
        for av in reported:
            if av.key:
                by_key[av.key] = av
        new = replace(old, reported_state=list(by_key.values()))
        self._devices[device_id] = new
        return new

    def patch_device_desired(
        self,
        device_id: str,
        desired: list[AttributeValueDto],
    ) -> None:
        """Optimistic update desired_state после команды."""
        old = self._devices.get(device_id)
        if old is None:
            return
        by_key = {av.key: av for av in old.desired_state}
        for av in desired:
            if av.key:
                by_key[av.key] = av
        self._devices[device_id] = replace(
            old, desired_state=list(by_key.values())
        )


__all__ = ["StateCache"]
