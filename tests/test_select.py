"""Tests for the SberHome select platform — sbermap-driven (PR #7).

Enum-fallback из кэша /devices/enums покрыт отдельно в
tests/test_select_enum_fallback.py — здесь базовое поведение:
создание, options из FeatureSpec, current_option, async_select_option.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory, Platform

from custom_components.sberhome.select import SberSbermapSelect, async_setup_entry
from tests.conftest import build_coordinator_caches

# Пылесос: SELECT-фича vacuum_cleaner_program с options из FeatureSpec.
MOCK_DEVICE_VACUUM_PROGRAM = {
    "id": "device_vacuum_1",
    "serial_number": "SN_VACUUM_001",
    "name": {"name": "Test Vacuum"},
    "image_set_type": "vacuum_cleaner",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-VACUUM"},
    "desired_state": [],
    "reported_state": [
        {"key": "vacuum_cleaner_status", "enum_value": "cleaning"},
        {"key": "vacuum_cleaner_program", "enum_value": "smart"},
    ],
    "attributes": [],
}


def _door_payload(sensitive_value: str) -> dict:
    """Датчик двери: SELECT-фича sensor_sensitive (CONFIG)."""
    return {
        "id": "device_door_1",
        "serial_number": "SN_DOOR_001",
        "name": {"name": "Test Door Sensor"},
        "image_set_type": "sensor_door",
        "sw_version": "1.0.0",
        "device_info": {"manufacturer": "Sber", "model": "SBDV-DOOR"},
        "desired_state": [],
        "reported_state": [
            {"key": "doorcontact_state", "bool_value": False},
            {"key": "sensor_sensitive", "enum_value": sensitive_value},
        ],
        "attributes": [],
    }


def _make_coordinator(raw_devices: dict) -> MagicMock:
    """Coordinator-like MagicMock с sbermap-кэшами и AsyncMock на отправку команд."""
    coord = MagicMock()
    coord.data = raw_devices
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    coord.async_send_device_state = AsyncMock()
    return coord


def _select_by_id(coord, device_id: str, unique_id: str) -> SberSbermapSelect:
    """Helper: построить SberSbermapSelect для конкретного unique_id из entities."""
    ent = next(e for e in coord.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapSelect(coord, device_id, ent)


class TestVacuumProgramSelect:
    """vacuum_cleaner_program — select с options из FeatureSpec."""

    @pytest.fixture
    def coordinator(self):
        return _make_coordinator({"device_vacuum_1": MOCK_DEVICE_VACUUM_PROGRAM})

    @pytest.fixture
    def entity(self, coordinator):
        return _select_by_id(
            coordinator, "device_vacuum_1", "device_vacuum_1_vacuum_cleaner_program"
        )

    def test_unique_id(self, entity):
        """unique_id = device_id + суффикс фичи."""
        assert entity._attr_unique_id == "device_vacuum_1_vacuum_cleaner_program"

    def test_name_and_translation_key_from_suffix(self, entity):
        """Суффикс становится display-именем и translation_key."""
        assert entity._attr_name == "Vacuum Cleaner Program"
        assert entity._attr_translation_key == "vacuum_cleaner_program"

    def test_options_from_feature_spec(self, entity):
        """options приходят из FeatureSpec без похода в enum-кэш."""
        assert entity._attr_options == ["perimeter", "spot", "smart"]

    def test_icon(self, entity):
        """Иконка из FeatureSpec."""
        assert entity._attr_icon == "mdi:robot-vacuum"

    def test_current_option(self, entity):
        """reported 'smart' входит в options → current_option='smart'."""
        assert entity.current_option == "smart"

    def test_current_option_none_when_entity_disappears(self, coordinator, entity):
        """Устройство пропало из entities-кэша → current_option=None."""
        coordinator.entities["device_vacuum_1"] = []
        assert entity.current_option is None

    async def test_select_option_sends_enum_command(self, coordinator, entity):
        """async_select_option → enum_value по state_attribute_key."""
        await entity.async_select_option("spot")
        coordinator.async_send_device_state.assert_awaited_once()
        device_id, attrs = coordinator.async_send_device_state.await_args.args
        assert device_id == "device_vacuum_1"
        assert attrs[0].key == "vacuum_cleaner_program"
        assert attrs[0].enum_value == "spot"


class TestSensorSensitiveSelect:
    """sensor_sensitive — CONFIG select датчика двери."""

    @pytest.fixture
    def entity(self):
        coordinator = _make_coordinator({"device_door_1": _door_payload("auto")})
        return _select_by_id(coordinator, "device_door_1", "device_door_1_sensor_sensitive")

    def test_options_from_feature_spec(self, entity):
        """options чувствительности — auto/high."""
        assert entity._attr_options == ["auto", "high"]

    def test_current_option(self, entity):
        """reported 'auto' → current_option='auto'."""
        assert entity.current_option == "auto"

    def test_entity_category_config(self, entity):
        """sensor_sensitive — конфигурационная сущность."""
        assert entity._attr_entity_category is EntityCategory.CONFIG

    def test_current_option_none_when_state_not_in_options(self):
        """Значение вне options (мусор от API) → current_option=None."""
        coordinator = _make_coordinator({"device_door_1": _door_payload("turbo")})
        entity = _select_by_id(coordinator, "device_door_1", "device_door_1_sensor_sensitive")
        assert entity.current_option is None


class TestAsyncSetupEntry:
    async def test_creates_only_select_entities(self):
        """setup_entry создаёт только SELECT (VACUUM/BINARY_SENSOR отфильтрованы)."""
        coordinator = _make_coordinator(
            {
                "device_vacuum_1": MOCK_DEVICE_VACUUM_PROGRAM,
                "device_door_1": _door_payload("auto"),
            }
        )
        # У устройств есть и не-SELECT primary — проверяем фильтр по платформе.
        vacuum_platforms = {e.platform for e in coordinator.entities["device_vacuum_1"]}
        assert Platform.VACUUM in vacuum_platforms

        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        assert len(captured) == 2
        assert all(isinstance(e, SberSbermapSelect) for e in captured)
        unique_ids = {e._attr_unique_id for e in captured}
        assert unique_ids == {
            "device_vacuum_1_vacuum_cleaner_program",
            "device_door_1_sensor_sensitive",
        }
