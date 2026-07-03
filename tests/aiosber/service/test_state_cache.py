"""Tests for StateCache — typed in-memory state store."""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto import (
    AttributeValueDto,
    AttributeValueType,
    DeviceDto,
)
from custom_components.sberhome.aiosber.dto.union import (
    UnionDto,
    UnionTreeDto,
    UnionType,
)
from custom_components.sberhome.aiosber.service.state_cache import StateCache


def _make_tree() -> UnionTreeDto:
    """Build a realistic tree: Home → Room(Кухня) with 2 devices."""
    return UnionTreeDto(
        union=UnionDto(id="home-1", name="Дом", group_type=UnionType.HOME),
        devices=[
            DeviceDto(id="dev-orphan", name="Orphan"),
        ],
        children=[
            UnionTreeDto(
                union=UnionDto(
                    id="room-kitchen",
                    name="Кухня",
                    group_type=UnionType.ROOM,
                    device_ids=["dev-1", "dev-2"],
                ),
                devices=[
                    DeviceDto(
                        id="dev-1",
                        name="Лампа",
                        image_set_type="bulb_sber",
                        reported_state=[
                            AttributeValueDto(
                                key="on_off",
                                type=AttributeValueType.BOOL,
                                bool_value=True,
                            ),
                        ],
                    ),
                    DeviceDto(id="dev-2", name="Розетка"),
                ],
                children=[],
            ),
            UnionTreeDto(
                union=UnionDto(
                    id="room-bedroom",
                    name="Спальня",
                    group_type=UnionType.ROOM,
                ),
                devices=[
                    DeviceDto(id="dev-3", name="Ночник"),
                ],
                children=[],
            ),
        ],
    )


def test_update_from_tree_populates_devices():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    assert len(cache.get_all_devices()) == 4
    assert cache.get_device("dev-1") is not None
    assert cache.get_device("dev-orphan") is not None


def test_update_from_tree_populates_groups():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    groups = cache.get_all_groups()
    assert "home-1" in groups
    assert "room-kitchen" in groups
    assert "room-bedroom" in groups


def test_get_rooms():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    rooms = cache.get_rooms()
    names = {r.name for r in rooms}
    assert names == {"Кухня", "Спальня"}


def test_get_home():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    home = cache.get_home()
    assert home is not None
    assert home.name == "Дом"


def test_device_room_mapping():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    assert cache.device_room("dev-1") == "Кухня"
    assert cache.device_room("dev-2") == "Кухня"
    assert cache.device_room("dev-3") == "Спальня"
    assert cache.device_room("dev-orphan") is None  # top-level, not in room


def test_device_room_id():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    assert cache.device_room_id("dev-1") == "room-kitchen"
    assert cache.device_room_id("dev-3") == "room-bedroom"


def test_patch_device_state():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    new_dto = cache.patch_device_state(
        "dev-1",
        [AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=False)],
    )
    assert new_dto is not None
    assert new_dto.reported("on_off").bool_value is False


def test_patch_device_state_syncs_desired():
    """WS DEVICE_STATE должен синхронизировать desired_state — иначе light
    entity (читает desired) не увидит изменений из приложения «Салют!»."""
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    new_dto = cache.patch_device_state(
        "dev-1",
        [AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=False)],
    )
    assert new_dto is not None
    # И reported, и desired содержат новое значение.
    assert new_dto.reported("on_off").bool_value is False
    assert any(av.key == "on_off" and av.bool_value is False for av in new_dto.desired_state)


def test_patch_device_state_unknown_device():
    cache = StateCache()
    assert cache.patch_device_state("unknown", []) is None


def test_patch_device_desired():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    cache.patch_device_desired(
        "dev-1",
        [AttributeValueDto.of_bool("on_off", False)],
    )
    dto = cache.get_device("dev-1")
    assert any(av.key == "on_off" and av.bool_value is False for av in dto.desired_state)


def test_device_ids():
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    ids = cache.device_ids()
    assert ids == frozenset({"dev-1", "dev-2", "dev-3", "dev-orphan"})


def test_get_tree():
    cache = StateCache()
    tree = _make_tree()
    cache.update_from_tree(tree)
    assert cache.get_tree() is tree


# ---------------------------------------------------------------------------
# Multi-home (issue #2)
# ---------------------------------------------------------------------------


def _make_multi_home_tree() -> UnionTreeDto:
    """Tree с двумя HOME-узлами — «Мой дом» и «Дача»."""
    return UnionTreeDto(
        union=None,  # virtual root
        devices=[],
        children=[
            UnionTreeDto(
                union=UnionDto(id="home-main", name="Мой дом", group_type=UnionType.HOME),
                devices=[],
                children=[
                    UnionTreeDto(
                        union=UnionDto(
                            id="room-main-kitchen",
                            name="Кухня",
                            group_type=UnionType.ROOM,
                        ),
                        devices=[
                            DeviceDto(id="dev-main-1", name="Лампа кухни"),
                        ],
                        children=[],
                    ),
                ],
            ),
            UnionTreeDto(
                union=UnionDto(id="home-dacha", name="Дача", group_type=UnionType.HOME),
                devices=[
                    DeviceDto(id="dev-dacha-orphan", name="Орфан дачи"),
                ],
                children=[
                    UnionTreeDto(
                        union=UnionDto(
                            id="room-dacha-veranda",
                            name="Веранда",
                            group_type=UnionType.ROOM,
                        ),
                        devices=[
                            DeviceDto(id="dev-dacha-1", name="Лента веранды"),
                        ],
                        children=[],
                    ),
                ],
            ),
        ],
    )


def test_get_homes_returns_all_home_nodes():
    cache = StateCache()
    cache.update_from_tree(_make_multi_home_tree())
    homes = cache.get_homes()
    names = {h.name for h in homes}
    assert names == {"Мой дом", "Дача"}


def test_get_home_returns_first_for_legacy_callers():
    """`get_home()` остаётся доступным — возвращает первый из get_homes()."""
    cache = StateCache()
    cache.update_from_tree(_make_multi_home_tree())
    home = cache.get_home()
    assert home is not None
    assert home.id == "home-main"  # первый по обходу tree


def test_device_home_id_maps_through_subtree():
    cache = StateCache()
    cache.update_from_tree(_make_multi_home_tree())
    # device внутри room того дома
    assert cache.device_home_id("dev-main-1") == "home-main"
    assert cache.device_home_id("dev-dacha-1") == "home-dacha"
    # orphan device на уровне дома (без room) — home всё равно есть
    assert cache.device_home_id("dev-dacha-orphan") == "home-dacha"


def test_device_home_name_maps_through_subtree():
    cache = StateCache()
    cache.update_from_tree(_make_multi_home_tree())
    assert cache.device_home_name("dev-main-1") == "Мой дом"
    assert cache.device_home_name("dev-dacha-1") == "Дача"


def test_device_home_id_returns_none_for_unknown():
    cache = StateCache()
    cache.update_from_tree(_make_multi_home_tree())
    assert cache.device_home_id("does-not-exist") is None


def test_get_rooms_filters_by_home_id():
    cache = StateCache()
    cache.update_from_tree(_make_multi_home_tree())
    rooms_main = cache.get_rooms(home_id="home-main")
    rooms_dacha = cache.get_rooms(home_id="home-dacha")
    assert {r.name for r in rooms_main} == {"Кухня"}
    assert {r.name for r in rooms_dacha} == {"Веранда"}


def test_get_rooms_without_filter_returns_all():
    """BC: get_rooms() без аргумента продолжает возвращать всё."""
    cache = StateCache()
    cache.update_from_tree(_make_multi_home_tree())
    rooms = cache.get_rooms()
    assert {r.name for r in rooms} == {"Кухня", "Веранда"}


def test_single_home_tree_still_works():
    """Регрессия: legacy single-home tree продолжает корректно мапиться."""
    cache = StateCache()
    cache.update_from_tree(_make_tree())
    homes = cache.get_homes()
    assert len(homes) == 1
    assert homes[0].id == "home-1"
    assert cache.device_home_id("dev-1") == "home-1"
    assert cache.device_home_id("dev-orphan") == "home-1"  # под HOME root, без room


# ---------------------------------------------------------------------------
# update_from_flat (multi-home unified flat-list refresh)
# ---------------------------------------------------------------------------


def _flat_data() -> tuple[list, list, list, list]:
    """2 homes, по 1 room в каждом, devices в обоих + один top-level."""
    homes = [
        UnionDto(id="home-main", name="Мой дом", group_type=UnionType.HOME),
        UnionDto(id="home-dacha", name="Дача", group_type=UnionType.HOME),
    ]
    rooms = [
        UnionDto(
            id="room-kitchen",
            name="Кухня",
            group_type=UnionType.ROOM,
            parent_id="home-main",
        ),
        UnionDto(
            id="room-veranda",
            name="Веранда",
            group_type=UnionType.ROOM,
            parent_id="home-dacha",
        ),
    ]
    groups: list[UnionDto] = []
    devices = [
        # Device в комнате «Мой дом» / Кухня.
        DeviceDto(id="dev-main-lamp", name="Лампа кухни", group_ids=["room-kitchen"]),
        # Device в комнате «Дача» / Веранда.
        DeviceDto(id="dev-dacha-strip", name="Лента веранды", group_ids=["room-veranda"]),
        # Top-level device напрямую под home (SberBoom Home pattern).
        DeviceDto(id="dev-boom", name="SberBoom Home", group_ids=["home-main"]),
    ]
    return homes, rooms, groups, devices


def test_update_from_flat_homes():
    cache = StateCache()
    homes, rooms, groups, devices = _flat_data()
    cache.update_from_flat(homes, rooms, groups, devices)
    got = cache.get_homes()
    assert {h.name for h in got} == {"Мой дом", "Дача"}


def test_update_from_flat_device_home_via_room():
    """device.group_ids[0] = room.id → home через room.parent_id."""
    cache = StateCache()
    cache.update_from_flat(*_flat_data())
    assert cache.device_home_id("dev-main-lamp") == "home-main"
    assert cache.device_home_name("dev-main-lamp") == "Мой дом"
    assert cache.device_room_id("dev-main-lamp") == "room-kitchen"
    assert cache.device_room("dev-main-lamp") == "Кухня"


def test_update_from_flat_device_home_direct():
    """device.group_ids[0] = home.id → top-level (SberBoom pattern)."""
    cache = StateCache()
    cache.update_from_flat(*_flat_data())
    assert cache.device_home_id("dev-boom") == "home-main"
    assert cache.device_home_name("dev-boom") == "Мой дом"
    # У top-level device нет room.
    assert cache.device_room_id("dev-boom") is None


def test_update_from_flat_separates_homes():
    """Devices разных домов не путаются."""
    cache = StateCache()
    cache.update_from_flat(*_flat_data())
    assert cache.device_home_id("dev-dacha-strip") == "home-dacha"
    assert cache.device_home_name("dev-dacha-strip") == "Дача"
    assert cache.device_room("dev-dacha-strip") == "Веранда"


def test_update_from_flat_get_rooms_filter():
    cache = StateCache()
    cache.update_from_flat(*_flat_data())
    main_rooms = cache.get_rooms(home_id="home-main")
    dacha_rooms = cache.get_rooms(home_id="home-dacha")
    assert {r.name for r in main_rooms} == {"Кухня"}
    assert {r.name for r in dacha_rooms} == {"Веранда"}


def test_update_from_flat_unknown_group_id():
    """Device с group_ids указывающим на несуществующую группу — orphan."""
    cache = StateCache()
    devices = [DeviceDto(id="orphan", name="Orphan", group_ids=["does-not-exist"])]
    cache.update_from_flat([], [], [], devices)
    assert cache.get_device("orphan") is not None
    assert cache.device_home_id("orphan") is None
    assert cache.device_room_id("orphan") is None


def test_state_cache_devices_by_group_index():
    """После update_from_flat() reverse-index group → devices корректен."""
    cache = StateCache()
    cache.update_from_flat(
        homes=[UnionDto(id="home-1", name="Дом", group_type=UnionType.HOME)],
        rooms=[],
        groups=[
            UnionDto(id="grp-living", name="Освещение прихожей", group_type=UnionType.GROUP),
            UnionDto(id="grp-kitchen", name="Кухонные приборы", group_type=UnionType.GROUP),
        ],
        devices=[
            DeviceDto(id="dev-1", group_ids=["grp-living"]),
            DeviceDto(id="dev-2", group_ids=["grp-living", "grp-kitchen"]),
            DeviceDto(id="dev-3", group_ids=["grp-kitchen"]),
            DeviceDto(id="dev-orphan", group_ids=[]),
        ],
    )
    assert sorted(cache.get_group_devices("grp-living")) == ["dev-1", "dev-2"]
    assert sorted(cache.get_group_devices("grp-kitchen")) == ["dev-2", "dev-3"]
    assert cache.get_group_devices("nonexistent") == []


# ---------------------------------------------------------------------------
# Raw payload cache
# ---------------------------------------------------------------------------


def test_update_from_flat_raw_devices_cache():
    """raw_devices=... наполняет _raw_devices для UI/diagnostics."""
    cache = StateCache()
    homes, rooms, groups, devices = _flat_data()
    raw = {
        "dev-main-lamp": {"id": "dev-main-lamp", "images": {"on": "/url1"}},
        "dev-boom": {"id": "dev-boom", "images": {"on": "/url2"}},
    }
    cache.update_from_flat(homes, rooms, groups, devices, raw_devices=raw)
    assert cache.get_raw_payload("dev-main-lamp") == raw["dev-main-lamp"]
    assert cache.get_raw_payload("dev-boom") == raw["dev-boom"]
    assert cache.get_raw_payload("nonexistent") is None
    assert cache.get_all_raw_payloads() == raw


def test_update_from_flat_no_raw_keeps_previous():
    """Если raw_devices=None — старый raw cache не сбрасывается."""
    cache = StateCache()
    cache.update_from_flat([], [], [], [], raw_devices={"x": {"id": "x"}})
    # Следующий refresh без raw_devices — не сбрасывает.
    cache.update_from_flat([], [], [], [])
    assert cache.get_raw_payload("x") == {"id": "x"}


# ---------------------------------------------------------------------------
# Enum dictionary
# ---------------------------------------------------------------------------


def test_set_enums_get_enum_values():
    cache = StateCache()
    cache.set_enums({"hvac_work_mode": ["cool", "heat"], "fan_speed": ["low"]})
    assert cache.get_enum_values("hvac_work_mode") == ["cool", "heat"]
    assert cache.get_enum_values("fan_speed") == ["low"]
    assert cache.get_enum_values("nonexistent") == []
    assert cache.get_enums() == {"hvac_work_mode": ["cool", "heat"], "fan_speed": ["low"]}


def test_enums_default_empty():
    cache = StateCache()
    assert cache.get_enums() == {}
    assert cache.get_enum_values("anything") == []


def test_set_enums_replaces_completely():
    cache = StateCache()
    cache.set_enums({"a": ["x"]})
    cache.set_enums({"b": ["y"]})
    assert cache.get_enums() == {"b": ["y"]}
    assert cache.get_enum_values("a") == []


# ---------------------------------------------------------------------------
# Race guard: full refresh не затирает локальные патчи, случившиеся
# ВО ВРЕМЯ HTTP-fetch'а (WS push / optimistic после команды).
# См. race-аудит: раньше update_from_flat делал self._devices = devices_map
# (wholesale replace) → включённая лампа «откатывалась» в UI.
# ---------------------------------------------------------------------------


def _bool_attr(key: str, value: bool) -> AttributeValueDto:
    return AttributeValueDto(key=key, type=AttributeValueType.BOOL, bool_value=value)


def _stale_snapshot() -> tuple[list, list, list, list]:
    """Снимок с device on_off=False + свежими метаданными (sw_version)."""
    homes = [UnionDto(id="home-1", name="Дом", group_type=UnionType.HOME)]
    devices = [
        DeviceDto(
            id="lamp-1",
            name="Лампа",
            sw_version="2.0-fresh-meta",
            group_ids=["home-1"],
            reported_state=[_bool_attr("on_off", False)],
            desired_state=[_bool_attr("on_off", False)],
        )
    ]
    return homes, [], [], devices


def test_refresh_does_not_clobber_ws_patch_during_fetch():
    """WS patch пришёл ПОСЛЕ старта fetch'а → state сохраняется,
    metadata берётся из снимка."""
    import time

    cache = StateCache()
    # Начальное состояние: лампа выключена, старые метаданные.
    cache.update_from_flat(
        [UnionDto(id="home-1", name="Дом", group_type=UnionType.HOME)],
        [],
        [],
        [
            DeviceDto(
                id="lamp-1",
                name="Лампа",
                sw_version="1.0-old",
                group_ids=["home-1"],
                reported_state=[_bool_attr("on_off", False)],
            )
        ],
    )

    # HTTP fetch стартует (снимок сервера с on_off=False).
    fetch_started_at = time.monotonic()

    # WS push во время fetch'а: юзер включил лампу.
    cache.patch_device_state("lamp-1", [_bool_attr("on_off", True)])

    # Fetch завершился устаревшим снимком (on_off=False), но с
    # обновлённой метадатой (sw_version=2.0).
    cache.update_from_flat(*_stale_snapshot(), fetch_started_at=fetch_started_at)

    dev = cache.get_device("lamp-1")
    assert dev is not None
    # State — из локального патча (лампа ВКЛЮЧЕНА, не откатилась).
    on_off = next(av for av in dev.reported_state if av.key == "on_off")
    assert on_off.bool_value is True
    # Metadata — из свежего снимка.
    assert dev.sw_version == "2.0-fresh-meta"


def test_refresh_does_not_clobber_optimistic_desired_during_fetch():
    """Optimistic desired-патч (после команды) тоже защищён."""
    import time

    cache = StateCache()
    cache.update_from_flat(*_stale_snapshot())

    fetch_started_at = time.monotonic()
    cache.patch_device_desired("lamp-1", [_bool_attr("on_off", True)])
    cache.update_from_flat(*_stale_snapshot(), fetch_started_at=fetch_started_at)

    dev = cache.get_device("lamp-1")
    assert dev is not None
    desired = next(av for av in dev.desired_state if av.key == "on_off")
    assert desired.bool_value is True


def test_refresh_applies_snapshot_when_patch_was_before_fetch():
    """Патч ДО старта fetch'а → снимок сервера уже включает его
    (или новее) → заменяем нормально, guard не мешает."""
    import time

    cache = StateCache()
    cache.update_from_flat(*_stale_snapshot())

    # Патч ПЕРЕД fetch'ем.
    cache.patch_device_state("lamp-1", [_bool_attr("on_off", True)])
    fetch_started_at = time.monotonic()

    # Fetch стартовал после патча — его снимок authoritative.
    cache.update_from_flat(*_stale_snapshot(), fetch_started_at=fetch_started_at)

    dev = cache.get_device("lamp-1")
    assert dev is not None
    on_off = next(av for av in dev.reported_state if av.key == "on_off")
    # Снимок (False) применён — патч был до fetch'а, сервер его уже видел.
    assert on_off.bool_value is False


def test_refresh_without_fetch_started_at_is_legacy_full_replace():
    """Без fetch_started_at (тесты, legacy-код) — старое поведение."""
    cache = StateCache()
    cache.update_from_flat(*_stale_snapshot())
    cache.patch_device_state("lamp-1", [_bool_attr("on_off", True)])
    cache.update_from_flat(*_stale_snapshot())  # no fetch_started_at

    dev = cache.get_device("lamp-1")
    assert dev is not None
    on_off = next(av for av in dev.reported_state if av.key == "on_off")
    assert on_off.bool_value is False  # заменено — guard выключен


def test_local_write_timestamps_pruned_for_removed_devices():
    """Устройство исчезло из аккаунта → его timestamp вычищается,
    dict не растёт бесконечно."""
    import time

    cache = StateCache()
    cache.update_from_flat(*_stale_snapshot())
    cache.patch_device_state("lamp-1", [_bool_attr("on_off", True)])
    assert "lamp-1" in cache._last_local_write_at

    # Новый снимок БЕЗ lamp-1 (устройство удалено из Sber).
    fetch_started_at = time.monotonic()
    cache.update_from_flat(
        [UnionDto(id="home-1", name="Дом", group_type=UnionType.HOME)],
        [],
        [],
        [],
        fetch_started_at=fetch_started_at,
    )
    assert cache.get_device("lamp-1") is None
    assert "lamp-1" not in cache._last_local_write_at


def test_update_from_tree_also_protected():
    """Tree-fallback path (legacy) — тот же guard."""
    import time

    cache = StateCache()
    cache.update_from_tree(_make_tree())

    fetch_started_at = time.monotonic()
    # WS push во время fetch: dev-1 включён.
    cache.patch_device_state("dev-1", [_bool_attr("on_off", False)])
    # Приходит устаревший tree (dev-1 on_off=True из _make_tree).
    cache.update_from_tree(_make_tree(), fetch_started_at=fetch_started_at)

    dev = cache.get_device("dev-1")
    assert dev is not None
    on_off = next(av for av in dev.reported_state if av.key == "on_off")
    assert on_off.bool_value is False  # локальный патч сохранён
