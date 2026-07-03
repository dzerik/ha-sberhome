"""Tests for the SberHome vacuum platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.vacuum import VacuumActivity, VacuumEntityFeature
from homeassistant.const import Platform

from custom_components.sberhome.vacuum import SberSbermapVacuum, async_setup_entry
from tests.conftest import build_coordinator_caches


def _vacuum_payload(device_id: str, reported: list[dict]) -> dict:
    """Raw-dict payload робота-пылесоса с заданным reported_state."""
    return {
        "id": device_id,
        "serial_number": f"SN_{device_id.upper()}",
        "name": {"name": "Test Vacuum"},
        "image_set_type": "vacuum_cleaner",
        "sw_version": "1.0.0",
        "device_info": {"manufacturer": "Sber", "model": "SBDV-VACUUM"},
        "desired_state": [],
        "reported_state": reported,
        "attributes": [],
    }


MOCK_DEVICE_VACUUM_CLEANING = _vacuum_payload(
    "device_vacuum_1",
    [
        {"key": "vacuum_cleaner_status", "enum_value": "cleaning"},
        {"key": "battery_percentage", "integer_value": 67},
        {"key": "vacuum_cleaner_program", "enum_value": "smart"},
    ],
)


def _make_coordinator(raw_devices: dict) -> MagicMock:
    """Coordinator-like MagicMock с sbermap-кэшами и AsyncMock на отправку команд."""
    coord = MagicMock()
    coord.data = raw_devices
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    coord.async_send_device_state = AsyncMock()
    return coord


def _vacuum(coord, device_id: str) -> SberSbermapVacuum:
    """Helper: построить SberSbermapVacuum из primary VACUUM entity."""
    ent = next(e for e in coord.entities[device_id] if e.platform is Platform.VACUUM)
    return SberSbermapVacuum(coord, device_id, ent)


def _vacuum_with_reported(reported: list[dict]) -> SberSbermapVacuum:
    """Helper: пылесос из свежего координатора с заданным reported_state."""
    coord = _make_coordinator({"device_vacuum_1": _vacuum_payload("device_vacuum_1", reported)})
    return _vacuum(coord, "device_vacuum_1")


class TestVacuumState:
    """Read path: activity/battery из HaEntityData."""

    @pytest.fixture
    def coordinator(self):
        return _make_coordinator({"device_vacuum_1": MOCK_DEVICE_VACUUM_CLEANING})

    @pytest.fixture
    def entity(self, coordinator):
        return _vacuum(coordinator, "device_vacuum_1")

    def test_unique_id(self, entity):
        """Primary entity — unique_id без суффикса, равен device id."""
        assert entity._attr_unique_id == "device_vacuum_1"

    def test_supported_features(self, entity):
        """Заявлены start/pause/stop/return_home/locate (без deprecated BATTERY/STATE)."""
        features = entity.supported_features
        assert features & VacuumEntityFeature.START
        assert features & VacuumEntityFeature.PAUSE
        assert features & VacuumEntityFeature.STOP
        assert features & VacuumEntityFeature.RETURN_HOME
        assert features & VacuumEntityFeature.LOCATE

    def test_activity_cleaning(self, entity):
        """vacuum_cleaner_status='cleaning' → VacuumActivity.CLEANING."""
        assert entity.activity is VacuumActivity.CLEANING

    def test_battery_level(self, entity):
        """battery_percentage=67 → battery_level=67."""
        assert entity.battery_level == 67

    def test_activity_docked_when_charging(self):
        """Sber-статус 'charging' маппится в DOCKED."""
        entity = _vacuum_with_reported([{"key": "vacuum_cleaner_status", "enum_value": "charging"}])
        assert entity.activity is VacuumActivity.DOCKED

    def test_activity_idle_when_status_unknown(self):
        """Неизвестный Sber-статус → fallback IDLE."""
        entity = _vacuum_with_reported(
            [{"key": "vacuum_cleaner_status", "enum_value": "levitating"}]
        )
        assert entity.activity is VacuumActivity.IDLE

    def test_activity_none_when_status_missing(self):
        """Пылесос без vacuum_cleaner_status в reported → activity=None."""
        entity = _vacuum_with_reported([{"key": "battery_percentage", "integer_value": 50}])
        assert entity.activity is None

    def test_battery_none_when_missing(self):
        """Нет battery_percentage в reported → battery_level=None."""
        entity = _vacuum_with_reported([{"key": "vacuum_cleaner_status", "enum_value": "cleaning"}])
        assert entity.battery_level is None

    def test_activity_none_when_entity_disappears(self, coordinator, entity):
        """Устройство пропало из entities-кэша → activity и battery None."""
        coordinator.entities["device_vacuum_1"] = []
        assert entity.activity is None
        assert entity.battery_level is None


class TestVacuumCommands:
    """Write path: каждая команда → enum vacuum_cleaner_command."""

    @pytest.fixture
    def coordinator(self):
        return _make_coordinator({"device_vacuum_1": MOCK_DEVICE_VACUUM_CLEANING})

    @pytest.fixture
    def entity(self, coordinator):
        return _vacuum(coordinator, "device_vacuum_1")

    @pytest.mark.parametrize(
        ("method", "command"),
        [
            ("async_start", "start"),
            ("async_pause", "pause"),
            ("async_stop", "stop"),
            ("async_return_to_base", "return_to_base"),
            ("async_locate", "locate"),
        ],
    )
    async def test_command_sends_enum(self, coordinator, entity, method, command):
        """Каждый метод шлёт enum_value с именем команды в vacuum_cleaner_command."""
        await getattr(entity, method)()
        coordinator.async_send_device_state.assert_awaited_once()
        device_id, attrs = coordinator.async_send_device_state.await_args.args
        assert device_id == "device_vacuum_1"
        assert attrs[0].key == "vacuum_cleaner_command"
        assert attrs[0].enum_value == command


class TestAsyncSetupEntry:
    async def test_creates_only_vacuum_entities(self):
        """setup_entry создаёт только VACUUM (SELECT program отфильтрован)."""
        coordinator = _make_coordinator({"device_vacuum_1": MOCK_DEVICE_VACUUM_CLEANING})
        # У устройства есть и SELECT (vacuum_cleaner_program) — проверяем фильтр.
        platforms = {e.platform for e in coordinator.entities["device_vacuum_1"]}
        assert Platform.SELECT in platforms

        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        assert len(captured) == 1
        assert isinstance(captured[0], SberSbermapVacuum)
