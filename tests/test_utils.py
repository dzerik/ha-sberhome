"""Tests for the SberHome utility functions."""

from __future__ import annotations

from custom_components.sberhome.utils import extract_devices, find_from_list


def test_find_from_list_found():
    data = [{"key": "on_off", "bool_value": True}]
    result = find_from_list(data, "on_off")
    assert result is not None
    assert result["bool_value"] is True


def test_find_from_list_not_found():
    data = [{"key": "on_off", "bool_value": True}]
    assert find_from_list(data, "brightness") is None


def test_find_from_list_empty():
    assert find_from_list([], "anything") is None


def test_extract_devices_flat():
    tree = {"devices": [{"id": "a"}, {"id": "b"}], "children": []}
    result = extract_devices(tree)
    assert set(result.keys()) == {"a", "b"}


def test_extract_devices_nested():
    tree = {
        "devices": [{"id": "a"}],
        "children": [
            {"devices": [{"id": "b"}], "children": []},
            {
                "devices": [{"id": "c"}],
                "children": [
                    {"devices": [{"id": "d"}], "children": []},
                ],
            },
        ],
    }
    result = extract_devices(tree)
    assert set(result.keys()) == {"a", "b", "c", "d"}


def test_extract_devices_empty():
    tree = {"devices": [], "children": []}
    assert extract_devices(tree) == {}
