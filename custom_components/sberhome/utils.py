"""Utility functions for SberHome integration."""

from __future__ import annotations


def find_from_list(data: list[dict], key: str) -> dict | None:
    """Find an item by key in a list of dicts."""
    for item in data:
        if item["key"] == key:
            return item
    return None


def extract_devices(d: dict) -> dict:
    """Recursively extract devices from the device tree."""
    devices: dict = {device["id"]: device for device in d["devices"]}
    for children in d["children"]:
        devices.update(extract_devices(children))
    return devices
