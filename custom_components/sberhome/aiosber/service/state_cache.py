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
        self._device_to_home_id: dict[str, str] = {}
        self._device_to_home_name: dict[str, str] = {}

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

    def get_rooms(self, home_id: str | None = None) -> list[UnionDto]:
        """Все группы с type==ROOM, опционально фильтр по принадлежности дому.

        Args:
            home_id: если задан — вернуть только rooms, чьи устройства
                принадлежат указанному дому. Если None — все rooms (legacy).
        """
        from ..dto.union import UnionType

        rooms = [g for g in self._groups.values() if g.group_type is UnionType.ROOM]
        if home_id is None:
            return rooms
        # Room принадлежит дому если хотя бы одно её device мапится на этот home_id.
        return [r for r in rooms if r.id and self._room_home_id(r.id) == home_id]

    def _room_home_id(self, room_id: str) -> str | None:
        """Home id для room через первое попавшееся device в этой room."""
        for did, rid in self._device_to_room_id.items():
            if rid == room_id:
                return self._device_to_home_id.get(did)
        return None

    def get_home(self) -> UnionDto | None:
        """Первая группа с type==HOME — legacy single-home accessor.

        Используется intents/scenarios, которые пока работают только для
        primary home (multi-home — отдельный enhancement). Для UI и WS API
        используй `get_homes()` чтобы получить полный список.
        """
        homes = self.get_homes()
        return homes[0] if homes else None

    def get_homes(self) -> list[UnionDto]:
        """Все HOME-узлы в текущем tree (multi-home aware).

        Порядок сохраняется из dict insertion order — соответствует порядку
        обхода tree, что обычно совпадает с порядком домов в Sber-приложении.
        """
        from ..dto.union import UnionType

        return [g for g in self._groups.values() if g.group_type is UnionType.HOME]

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

    def device_home_id(self, device_id: str) -> str | None:
        """ID дома для устройства (или None)."""
        return self._device_to_home_id.get(device_id)

    def device_home_name(self, device_id: str) -> str | None:
        """Имя дома для устройства (или None)."""
        return self._device_to_home_name.get(device_id)

    # ------------------------------------------------------------------
    # Write — full refresh from tree
    # ------------------------------------------------------------------
    def update_from_tree(self, tree: UnionTreeDto) -> None:
        """Parse tree → populate devices, groups, room/home mappings.

        Вызывается после каждого polling refresh.
        """
        self._tree = tree
        devices: dict[str, DeviceDto] = {}
        groups: dict[str, UnionDto] = {}
        device_to_room_name: dict[str, str] = {}
        device_to_room_id: dict[str, str] = {}
        device_to_home_id: dict[str, str] = {}
        device_to_home_name: dict[str, str] = {}

        self._walk_tree(
            tree,
            devices,
            groups,
            device_to_room_name,
            device_to_room_id,
            device_to_home_id,
            device_to_home_name,
            current_home_id=None,
            current_home_name=None,
        )

        self._devices = devices
        self._groups = groups
        self._device_to_room_name = device_to_room_name
        self._device_to_room_id = device_to_room_id
        self._device_to_home_id = device_to_home_id
        self._device_to_home_name = device_to_home_name

        _LOGGER.debug(
            "StateCache updated: %d devices, %d groups, %d room mappings, %d home mappings",
            len(devices),
            len(groups),
            len(device_to_room_name),
            len(device_to_home_id),
        )

    def update_from_devices(self, devices: dict[str, DeviceDto]) -> None:
        """Fallback-путь: заполнить кэш только устройствами (без tree/groups).

        Используется когда гейтвей не вернул типизированное дерево — в этом
        случае groups/rooms мы восстановить не можем, но хотя бы устройства
        должны быть доступны платформам. Без этого coordinator лез в
        `state_cache._devices` напрямую (нарушение инкапсуляции).
        """
        self._devices = dict(devices)
        # Остальные структуры не трогаем — либо они уже пусты (первый refresh
        # до tree), либо остаются от прошлого успешного update_from_tree.

    def _walk_tree(
        self,
        node: UnionTreeDto,
        devices: dict[str, DeviceDto],
        groups: dict[str, UnionDto],
        device_to_room_name: dict[str, str],
        device_to_room_id: dict[str, str],
        device_to_home_id: dict[str, str],
        device_to_home_name: dict[str, str],
        current_home_id: str | None,
        current_home_name: str | None,
    ) -> None:
        """Рекурсивно обойти дерево, собирая devices, groups и home/room mappings.

        `current_home_id`/`current_home_name` пробрасываются вглубь и
        обновляются при заходе в HOME-узел. Каждое device наследует home
        от ближайшего предка-HOME.
        """
        from ..dto.union import UnionType

        union = node.union
        if union is not None and union.id:
            groups[union.id] = union

        # Если этот node — HOME, обновляем context для subtree.
        if union is not None and union.group_type is UnionType.HOME and union.id:
            current_home_id = union.id
            current_home_name = union.name

        # Определяем: этот node — комната?
        is_room = union is not None and union.group_type is UnionType.ROOM and union.name

        for device in node.devices:
            if device.id:
                devices[device.id] = device
                if is_room and union is not None:
                    device_to_room_name[device.id] = union.name  # type: ignore[arg-type]
                    device_to_room_id[device.id] = union.id  # type: ignore[arg-type]
                if current_home_id:
                    device_to_home_id[device.id] = current_home_id
                    if current_home_name:
                        device_to_home_name[device.id] = current_home_name

        for child in node.children:
            self._walk_tree(
                child,
                devices,
                groups,
                device_to_room_name,
                device_to_room_id,
                device_to_home_id,
                device_to_home_name,
                current_home_id,
                current_home_name,
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
        self._devices[device_id] = replace(old, desired_state=list(by_key.values()))


__all__ = ["StateCache"]
