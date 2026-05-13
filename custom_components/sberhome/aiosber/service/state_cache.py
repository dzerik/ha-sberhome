"""StateCache — typed in-memory state store.

Single source of truth для состояния всех устройств и групп.
Заменяет raw dict cache. WS-patch обновляет DTO напрямую.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING, Any

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
        # Raw payload cache — `device_id → raw dict` от Sber-API без
        # пост-обработки. Используется UI/diagnostics для извлечения
        # полей не покрытых DTO (images CDN paths, etc.). Наполняется
        # в `update_from_flat` параллельно с DTO.
        self._raw_devices: dict[str, dict] = {}
        # Sber `/devices/enums` — нормализованный справочник
        # `attribute_key → list[str]`. Fallback-источник для
        # `select.options` когда `device.attributes[].enum_values`
        # возвращается пустым. Best-effort populated в
        # `DeviceService.refresh()` при первом успешном refresh.
        self._enums: dict[str, list[str]] = {}
        # Light effects catalog — `/light/effects` каталог сцен. Best-effort
        # lazy-loaded в `DeviceService.refresh()`. Каждый элемент содержит
        # `{id, name, preview?, category?}`.
        self._light_effects: list[dict[str, Any]] = []
        # group_id → [device_id, ...] — reverse-index из device.group_ids.
        # Перестраивается в update_from_flat()/update_from_tree() каждый refresh.
        self._devices_by_group: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Read — devices
    # ------------------------------------------------------------------
    def get_device(self, device_id: str) -> DeviceDto | None:
        return self._devices.get(device_id)

    def get_all_devices(self) -> dict[str, DeviceDto]:
        return dict(self._devices)

    def device_ids(self) -> frozenset[str]:
        return frozenset(self._devices)

    def get_group_devices(self, group_id: str) -> list[str]:
        """Список device_id, входящих в Sber-group (любого type).

        Используется `SberGroupSwitch` для агрегации `is_on` и optimistic
        patch после bulk-команды. Возвращает копию.
        """
        return list(self._devices_by_group.get(group_id, []))

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
    # Read — raw payload cache
    # ------------------------------------------------------------------
    def get_raw_payload(self, device_id: str) -> dict | None:
        """Raw API payload для устройства (без DTO пост-обработки).

        Используется UI и diagnostics для извлечения полей не покрытых DTO
        (например `images` CDN paths). Возвращает None если device не в
        кеше.
        """
        return self._raw_devices.get(device_id)

    def get_all_raw_payloads(self) -> dict[str, dict]:
        """Все raw payloads, как dict by device_id."""
        return dict(self._raw_devices)

    # ------------------------------------------------------------------
    # Read — enums dictionary
    # ------------------------------------------------------------------
    def get_enums(self) -> dict[str, list[str]]:
        """Нормализованный enum-словарь из Sber `/devices/enums`.

        Empty если ещё не подтянут (best-effort fetch в refresh()).
        """
        return dict(self._enums)

    def get_enum_values(self, attribute_key: str) -> list[str]:
        """Shortcut: список enum-значений для конкретного `attribute_key`.

        Используется HA-платформами (select) для построения options когда
        `device.attributes[].enum_values` возвращается пустым.
        """
        return list(self._enums.get(attribute_key, ()))

    # ------------------------------------------------------------------
    # Write — раз-в-сессию данные (enums dict)
    # ------------------------------------------------------------------
    def set_enums(self, enums: dict[str, list[str]]) -> None:
        """Заменить enum-словарь полностью (вызывается из refresh)."""
        self._enums = dict(enums)

    # ------------------------------------------------------------------
    # Light effects catalog (best-effort, lazy-loaded в DeviceService.refresh)
    # ------------------------------------------------------------------
    def get_light_effects(self) -> list[dict[str, Any]]:
        """Каталог световых эффектов из `/light/effects`.

        Возвращает копию (не пустую только если refresh когда-то успешно
        её загрузил). Каждый элемент содержит `{id, name, preview?, category?}`.
        """
        return list(self._light_effects)

    def set_light_effects(self, catalog: list[dict[str, Any]]) -> None:
        """Сохранить каталог light-effects.

        Вызывается из `DeviceService.refresh()` best-effort'ом. Пустой
        list тоже валидное значение (значит API не вернул эффекты).

        Элементы копируются по отдельности (dict copy на каждом item),
        чтобы caller не мог случайно мутировать stored catalog.
        """
        self._light_effects = [dict(item) for item in catalog]

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
        self._rebuild_devices_by_group_index()

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
        self._rebuild_devices_by_group_index()
        # Остальные структуры не трогаем — либо они уже пусты (первый refresh
        # до tree), либо остаются от прошлого успешного update_from_tree.

    def update_from_flat(
        self,
        homes: list[UnionDto],
        rooms: list[UnionDto],
        groups: list[UnionDto],
        devices: list[DeviceDto],
        *,
        raw_devices: dict[str, dict] | None = None,
    ) -> None:
        """Multi-home aware refresh из 4 плоских списков.

        В отличие от `update_from_tree` (single-home — Sber `/device_groups/tree`
        отдаёт только дефолтный дом), эти 4 endpoint'а отдают полную картину
        аккаунта:
        - `/device_groups?group_type=HOME` — все дома
        - `/device_groups?group_type=ROOM` — все комнаты всех домов
        - `/device_groups?group_type=GROUP` — кастомные группы
        - `/devices?pagination` — все устройства

        Связи строятся локально:
        - **room → home**: `room.parent_id == home.id`
        - **device → room | home**: первый id из `device.group_ids`
          сматчится либо с room (значит device в комнате этого дома),
          либо с home (top-level device, например SberBoom).
        """
        groups_map: dict[str, UnionDto] = {}
        device_to_room_name: dict[str, str] = {}
        device_to_room_id: dict[str, str] = {}
        device_to_home_id: dict[str, str] = {}
        device_to_home_name: dict[str, str] = {}

        homes_by_id: dict[str, UnionDto] = {}
        rooms_by_id: dict[str, UnionDto] = {}

        for h in homes:
            if h.id:
                groups_map[h.id] = h
                homes_by_id[h.id] = h
        for r in rooms:
            if r.id:
                groups_map[r.id] = r
                rooms_by_id[r.id] = r
        for g in groups:
            if g.id:
                groups_map[g.id] = g

        devices_map: dict[str, DeviceDto] = {}
        for dev in devices:
            if not dev.id:
                continue
            devices_map[dev.id] = dev
            # Резолвим home/room через group_ids[0] (Sber всегда кладёт один).
            gids = dev.group_ids or []
            primary_gid = gids[0] if gids else None
            if primary_gid is None:
                continue
            room = rooms_by_id.get(primary_gid)
            if room is not None:
                # device в комнате → home через room.parent_id
                if room.name and dev.id:
                    device_to_room_name[dev.id] = room.name
                device_to_room_id[dev.id] = room.id  # type: ignore[assignment]
                home_id = room.parent_id
                if home_id:
                    device_to_home_id[dev.id] = home_id
                    home = homes_by_id.get(home_id)
                    if home is not None and home.name:
                        device_to_home_name[dev.id] = home.name
            elif primary_gid in homes_by_id:
                # device напрямую под home (top-level: SberBoom Home, и т.п.)
                device_to_home_id[dev.id] = primary_gid
                home = homes_by_id[primary_gid]
                if home.name:
                    device_to_home_name[dev.id] = home.name

        self._devices = devices_map
        self._groups = groups_map
        self._device_to_room_name = device_to_room_name
        self._device_to_room_id = device_to_room_id
        self._device_to_home_id = device_to_home_id
        self._device_to_home_name = device_to_home_name
        self._rebuild_devices_by_group_index()
        # Raw payloads — для UI/diagnostics (если переданы).
        if raw_devices is not None:
            self._raw_devices = dict(raw_devices)
        # `_tree` остаётся либо None, либо последний tree от legacy refresh —
        # consumer'ы tree должны мигрировать на flat-API.

        _LOGGER.debug(
            "StateCache (flat) updated: %d devices, %d groups (%d homes, %d rooms), "
            "%d room mappings, %d home mappings",
            len(devices_map),
            len(groups_map),
            len(homes_by_id),
            len(rooms_by_id),
            len(device_to_room_name),
            len(device_to_home_id),
        )

    def _rebuild_devices_by_group_index(self) -> None:
        """Перестроить reverse-index `group_id → [device_id, ...]`.

        Вызывается из всех `update_from_*` методов после построения
        `self._devices`. Учитывает все group_ids устройства (device может
        входить в несколько групп — например ROOM + custom GROUP).
        """
        index: dict[str, list[str]] = {}
        for device_id, dto in self._devices.items():
            for group_id in dto.group_ids or []:
                index.setdefault(group_id, []).append(device_id)
        self._devices_by_group = index

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
