"""Tests for the SberHome utility functions."""

from __future__ import annotations

from custom_components.sberhome.utils import extract_devices


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
