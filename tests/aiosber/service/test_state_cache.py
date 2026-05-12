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
