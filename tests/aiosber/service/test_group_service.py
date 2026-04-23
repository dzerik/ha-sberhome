"""Tests for GroupService."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.sberhome.aiosber.dto import DeviceDto
from custom_components.sberhome.aiosber.dto.union import UnionDto, UnionTreeDto, UnionType
from custom_components.sberhome.aiosber.service.group_service import GroupService
from custom_components.sberhome.aiosber.service.state_cache import StateCache


def _make_cache() -> StateCache:
    cache = StateCache()
    tree = UnionTreeDto(
        union=UnionDto(id="home", name="Дом", group_type=UnionType.HOME),
        devices=[],
        children=[
            UnionTreeDto(
                union=UnionDto(
                    id="r1",
                    name="Кухня",
                    group_type=UnionType.ROOM,
                    device_ids=["d1", "d2"],
                ),
                devices=[
                    DeviceDto(id="d1"),
                    DeviceDto(id="d2"),
                ],
                children=[],
            ),
            UnionTreeDto(
                union=UnionDto(id="r2", name="Зал", group_type=UnionType.ROOM),
                devices=[DeviceDto(id="d3")],
                children=[],
            ),
        ],
    )
    cache.update_from_tree(tree)
    return cache


def test_list_rooms():
    cache = _make_cache()
    svc = GroupService(api=MagicMock(), cache=cache)
    rooms = svc.list_rooms()
    names = {r.name for r in rooms}
    assert names == {"Кухня", "Зал"}


def test_get_home():
    cache = _make_cache()
    svc = GroupService(api=MagicMock(), cache=cache)
    home = svc.get_home()
    assert home is not None
    assert home.name == "Дом"


def test_room_for_device():
    cache = _make_cache()
    svc = GroupService(api=MagicMock(), cache=cache)
    assert svc.room_for_device("d1") == "Кухня"
    assert svc.room_for_device("d3") == "Зал"
    assert svc.room_for_device("nonexistent") is None


def test_devices_in_group():
    cache = _make_cache()
    svc = GroupService(api=MagicMock(), cache=cache)
    devices = svc.devices_in_group("r1")
    assert len(devices) == 2


def test_get_tree():
    cache = _make_cache()
    svc = GroupService(api=MagicMock(), cache=cache)
    tree = svc.get_tree()
    assert tree is not None
    assert len(tree.children) == 2


def test_list_all():
    cache = _make_cache()
    svc = GroupService(api=MagicMock(), cache=cache)
    all_groups = svc.list_all()
    assert len(all_groups) == 3  # home + 2 rooms
