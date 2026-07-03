"""Tests for the SberHome number platform — sbermap-driven (PR #7)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory, Platform, UnitOfTemperature, UnitOfTime

from custom_components.sberhome.number import SberSbermapNumber, async_setup_entry
from custom_components.sberhome.sbermap import HaEntityData
from tests.conftest import build_coordinator_caches

# LED-лента: единственная категория с NUMBER-фичей sleep_timer.
MOCK_DEVICE_LEDSTRIP_TIMER = {
    "id": "device_ledstrip_1",
    "serial_number": "SN_LEDSTRIP_001",
    "name": {"name": "Test LED Strip"},
    "image_set_type": "ledstrip_sber",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-00033"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": True},
        {"key": "sleep_timer", "integer_value": 30},
    ],
    "attributes": [],
}

# Чайник: NUMBER-фича kitchen_water_temperature_set с другим диапазоном.
MOCK_DEVICE_KETTLE_TEMP = {
    "id": "device_kettle_1",
    "serial_number": "SN_KETTLE_001",
    "name": {"name": "Test Kettle"},
    "image_set_type": "kettle",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-KETTLE"},
    "desired_state": [],
    "reported_state": [
        {"key": "on_off", "bool_value": False},
        {"key": "kitchen_water_temperature_set", "integer_value": 80},
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


def _number_by_id(coord, device_id: str, unique_id: str) -> SberSbermapNumber:
    """Helper: построить SberSbermapNumber для конкретного unique_id из entities."""
    ent = next(e for e in coord.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapNumber(coord, device_id, ent)


class TestSleepTimerNumber:
    """LED strip sleep_timer — CONFIG number с диапазоном 0-720 минут."""

    @pytest.fixture
    def coordinator(self):
        return _make_coordinator({"device_ledstrip_1": MOCK_DEVICE_LEDSTRIP_TIMER})

    @pytest.fixture
    def entity(self, coordinator):
        return _number_by_id(coordinator, "device_ledstrip_1", "device_ledstrip_1_sleep_timer")

    def test_unique_id(self, entity):
        """unique_id = device_id + суффикс фичи."""
        assert entity._attr_unique_id == "device_ledstrip_1_sleep_timer"

    def test_name_and_translation_key_from_suffix(self, entity):
        """Суффикс становится display-именем и translation_key."""
        assert entity._attr_name == "Sleep Timer"
        assert entity._attr_translation_key == "sleep_timer"

    def test_native_value(self, entity):
        """reported sleep_timer=30 → native_value=30."""
        assert entity.native_value == 30

    def test_range_from_feature_spec(self, entity):
        """min/max/step приходят из FeatureSpec (0-720, шаг 1)."""
        assert entity.native_min_value == 0
        assert entity.native_max_value == 720
        assert entity.native_step == 1

    def test_unit_of_measurement(self, entity):
        """Единица измерения — минуты."""
        assert entity.native_unit_of_measurement == UnitOfTime.MINUTES

    def test_entity_category_config(self, entity):
        """sleep_timer — конфигурационная сущность."""
        assert entity._attr_entity_category is EntityCategory.CONFIG

    def test_icon(self, entity):
        """Иконка из FeatureSpec."""
        assert entity._attr_icon == "mdi:timer"

    def test_native_value_none_when_entity_disappears(self, coordinator, entity):
        """Устройство пропало из entities-кэша → native_value=None."""
        coordinator.entities["device_ledstrip_1"] = []
        assert entity.native_value is None

    async def test_set_native_value_sends_integer_command(self, coordinator, entity):
        """async_set_native_value(45) → integer_value=45 по ключу sleep_timer."""
        await entity.async_set_native_value(45)
        coordinator.async_send_device_state.assert_awaited_once()
        device_id, attrs = coordinator.async_send_device_state.await_args.args
        assert device_id == "device_ledstrip_1"
        assert attrs[0].key == "sleep_timer"
        assert attrs[0].integer_value == 45

    async def test_set_native_value_applies_scale(self, coordinator):
        """scale из HaEntityData учитывается: raw = int(value / scale)."""
        ent = HaEntityData(
            platform=Platform.NUMBER,
            unique_id="device_ledstrip_1_custom_scaled",
            name="Custom Scaled",
            state=5,
            state_attribute_key="custom_scaled",
            scale=0.1,
        )
        num = SberSbermapNumber(coordinator, "device_ledstrip_1", ent)
        await num.async_set_native_value(12)
        _, attrs = coordinator.async_send_device_state.await_args.args
        assert attrs[0].key == "custom_scaled"
        assert attrs[0].integer_value == 120


class TestKettleTemperatureNumber:
    """Kettle kitchen_water_temperature_set — другой диапазон и unit."""

    @pytest.fixture
    def entity(self):
        coordinator = _make_coordinator({"device_kettle_1": MOCK_DEVICE_KETTLE_TEMP})
        return _number_by_id(
            coordinator, "device_kettle_1", "device_kettle_1_kitchen_water_temperature_set"
        )

    def test_native_value(self, entity):
        """reported 80°C → native_value=80."""
        assert entity.native_value == 80

    def test_range_from_feature_spec(self, entity):
        """Диапазон чайника 60-100°C с шагом 10."""
        assert entity.native_min_value == 60
        assert entity.native_max_value == 100
        assert entity.native_step == 10

    def test_unit_celsius(self, entity):
        """Единица измерения — градусы Цельсия."""
        assert entity.native_unit_of_measurement == UnitOfTemperature.CELSIUS


class TestAsyncSetupEntry:
    async def test_creates_only_number_entities(self):
        """setup_entry создаёт только NUMBER-сущности (LIGHT/SWITCH отфильтрованы)."""
        coordinator = _make_coordinator(
            {
                "device_ledstrip_1": MOCK_DEVICE_LEDSTRIP_TIMER,
                "device_kettle_1": MOCK_DEVICE_KETTLE_TEMP,
            }
        )
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        assert len(captured) == 2
        assert all(isinstance(e, SberSbermapNumber) for e in captured)
        unique_ids = {e._attr_unique_id for e in captured}
        assert unique_ids == {
            "device_ledstrip_1_sleep_timer",
            "device_kettle_1_kitchen_water_temperature_set",
        }
