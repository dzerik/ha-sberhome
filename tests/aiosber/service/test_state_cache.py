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
