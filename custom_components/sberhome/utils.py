"""Utility functions for SberHome integration."""

from __future__ import annotations


def extract_devices(d: dict) -> dict:
    """Recursively extract devices from the device tree."""
    devices: dict = {device["id"]: device for device in d["devices"]}
    for children in d["children"]:
        devices.update(extract_devices(children))
    return devices
