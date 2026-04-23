"""Tests for UnionDto, UnionTreeDto, UnionType."""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto.union import (
    UnionDto,
    UnionTreeDto,
    UnionType,
)


def test_union_type_enum():
    assert UnionType("ROOM") is UnionType.ROOM
    assert UnionType("HOME") is UnionType.HOME
    assert UnionType("GROUP") is UnionType.GROUP
    assert UnionType("NONE") is UnionType.NONE


def test_union_dto_from_dict():
    src = {
        "id": "room-1",
        "name": "Кухня",
        "parent_id": "home-1",
        "group_type": "ROOM",
        "device_ids": ["d1", "d2"],
        "sort_weight_int": 10,
    }
    dto = UnionDto.from_dict(src)
    assert dto.id == "room-1"
    assert dto.name == "Кухня"
    assert dto.group_type is UnionType.ROOM
    assert dto.device_ids == ["d1", "d2"]
    assert dto.sort_weight_int == 10


def test_union_tree_from_dict_remaps_group_key():
    """field key 'group' → field 'union'."""
    src = {
        "group": {"id": "g1", "name": "Home", "group_type": "HOME"},
        "devices": [{"id": "dev-1"}],
        "children": [],
    }
    tree = UnionTreeDto.from_dict(src)
    assert tree.union is not None
    assert tree.union.id == "g1"
    assert tree.union.group_type is UnionType.HOME
    assert len(tree.devices) == 1
    assert tree.devices[0].id == "dev-1"


def test_union_tree_recursive():
    src = {
        "group": {"id": "home", "group_type": "HOME"},
        "devices": [],
        "children": [
            {
                "group": {"id": "room-1", "name": "Зал", "group_type": "ROOM"},
                "devices": [{"id": "d1"}],
                "children": [],
            },
        ],
    }
    tree = UnionTreeDto.from_dict(src)
    assert len(tree.children) == 1
    child = tree.children[0]
    assert child.union.name == "Зал"
    assert child.devices[0].id == "d1"


def test_union_tree_without_group():
    """Root node may not have a 'group' key."""
    src = {"devices": [{"id": "d1"}], "children": []}
    tree = UnionTreeDto.from_dict(src)
    assert tree.union is None
    assert len(tree.devices) == 1
