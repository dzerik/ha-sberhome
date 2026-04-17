"""Tests for Feature-Descriptor mapper (3.0.0+)."""

from __future__ import annotations

from homeassistant.const import Platform

from custom_components.sberhome.aiosber.dto import DeviceDto
from custom_components.sberhome.sbermap.transform.mapper import (
    build_command,
    map_device_to_entities,
)


def _dto(image_set_type: str, reported: list[dict] | None = None, **kw) -> DeviceDto:
    data = {
        "id": "test-id",
        "name": "Test",
        "image_set_type": image_set_type,
        "reported_state": reported or [],
        **kw,
    }
    return DeviceDto.from_dict(data)


# =============================================================================
# Primary entity creation
# =============================================================================

class TestPrimaryEntities:
    def test_light_creates_light(self):
        dto = _dto("bulb_sber", [{"key": "on_off", "bool_value": True}])
        ents = map_device_to_entities(dto)
        platforms = {e.platform for e in ents}
        assert Platform.LIGHT in platforms

    def test_socket_creates_switch(self):
        dto = _dto("cat_socket", [{"key": "on_off", "bool_value": True}])
        ents = map_device_to_entities(dto)
        primary = next(e for e in ents if e.unique_id == "test-id")
        assert primary.platform is Platform.SWITCH

    def test_hvac_ac_creates_climate(self):
        dto = _dto("hvac_ac", [
            {"key": "on_off", "bool_value": True},
            {"key": "hvac_work_mode", "enum_value": "cool"},
        ])
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.CLIMATE for e in ents)

    def test_curtain_creates_cover(self):
        dto = _dto("cat_curtain", [
            {"key": "open_state", "enum_value": "open"},
            {"key": "open_percentage", "integer_value": 50},
        ])
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.COVER for e in ents)

    def test_vacuum_creates_vacuum(self):
        dto = _dto("cat_vacuum_cleaner", [
            {"key": "vacuum_cleaner_status", "enum_value": "idle"},
        ])
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.VACUUM for e in ents)

    def test_hub_creates_binary_sensor(self):
        dto = _dto("cat_hub", [{"key": "online", "bool_value": True}])
        ents = map_device_to_entities(dto)
        assert any(e.platform is Platform.BINARY_SENSOR for e in ents)

    def test_unknown_category_returns_empty(self):
        dto = _dto("completely_unknown_xyz", [])
        assert map_device_to_entities(dto) == []


# =============================================================================
# Extra entity auto-discovery
# =============================================================================

class TestAutoDiscovery:
    def test_battery_sensor_created(self):
        dto = _dto("cat_socket", [
            {"key": "on_off", "bool_value": True},
            {"key": "battery_percentage", "integer_value": 85},
        ])
        ents = map_device_to_entities(dto)
        battery = next((e for e in ents if "battery_percentage" in e.unique_id), None)
        assert battery is not None
        assert battery.platform is Platform.SENSOR
        assert battery.state == 85

    def test_unknown_feature_skipped(self):
        dto = _dto("cat_socket", [
            {"key": "on_off", "bool_value": True},
            {"key": "completely_unknown_feature", "string_value": "x"},
        ])
        ents = map_device_to_entities(dto)
        assert not any("completely_unknown" in e.unique_id for e in ents)

    def test_online_creates_connectivity(self):
        dto = _dto("cat_socket", [
            {"key": "on_off", "bool_value": True},
            {"key": "online", "bool_value": True},
        ])
        ents = map_device_to_entities(dto)
        online = next((e for e in ents if "online" in e.unique_id), None)
        assert online is not None
        assert online.platform is Platform.BINARY_SENSOR


# =============================================================================
# Category restrictions
# =============================================================================

class TestCategoryRestrictions:
    def test_child_lock_only_for_socket(self):
        dto_socket = _dto("cat_socket", [
            {"key": "on_off", "bool_value": True},
            {"key": "child_lock", "bool_value": False},
        ])
        dto_light = _dto("bulb_sber", [
            {"key": "on_off", "bool_value": True},
            {"key": "child_lock", "bool_value": False},
        ])
        socket_ents = map_device_to_entities(dto_socket)
        light_ents = map_device_to_entities(dto_light)
        assert any("child_lock" in e.unique_id for e in socket_ents)
        assert not any("child_lock" in e.unique_id for e in light_ents)

    def test_consumed_features_not_duplicated(self):
        """on_off consumed by SWITCH primary — no separate switch entity."""
        dto = _dto("cat_socket", [{"key": "on_off", "bool_value": True}])
        ents = map_device_to_entities(dto)
        switches = [e for e in ents if e.platform is Platform.SWITCH]
        assert len(switches) == 1  # only primary, no extra on_off


# =============================================================================
# Reverse mapper (build_command)
# =============================================================================

class TestBuildCommand:
    def test_bool_command(self):
        attrs = build_command("dev-1", on_off=True)
        assert len(attrs) == 1
        assert attrs[0].key == "on_off"
        assert attrs[0].bool_value is True

    def test_multi_feature_command(self):
        attrs = build_command("dev-1", on_off=True, light_brightness=200)
        keys = {a.key for a in attrs}
        assert keys == {"on_off", "light_brightness"}

    def test_none_values_skipped(self):
        attrs = build_command("dev-1", on_off=True, light_brightness=None)
        assert len(attrs) == 1

    def test_unknown_feature_passthrough(self):
        attrs = build_command("dev-1", unknown_feature=42)
        assert attrs[0].key == "unknown_feature"
        assert attrs[0].integer_value == 42

    def test_enum_command(self):
        attrs = build_command("dev-1", hvac_work_mode="cool")
        assert attrs[0].enum_value == "cool"
