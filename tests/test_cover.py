"""Tests for SberHome cover platform — sbermap-driven (PR #5 + bidirectional PR #9).

Проверяем:
- создание entities из coordinator.entities (Platform.COVER);
- маппинг state из reported_state (open_percentage/open_state);
- фичи по категориям (curtain/gate — полный набор, valve — только open/close);
- командные методы → coordinator.async_send_device_state;
- edge cases: пропавшая entity.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.cover import CoverDeviceClass, CoverEntityFeature, CoverState
from homeassistant.const import Platform

from custom_components.sberhome.aiosber.dto import AttributeValueDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.cover import SberSbermapCover, async_setup_entry
from custom_components.sberhome.sbermap import HaEntityData

from .conftest import build_coordinator_caches

# Штора наполовину открыта: reported open_percentage=70, open_state=opened.
MOCK_CURTAIN = {
    "id": "curtain_1",
    "serial_number": "SN_CURTAIN_001",
    "name": {"name": "Test Curtain"},
    "image_set_type": "curtain",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-CURTAIN"},
    "desired_state": [],
    "reported_state": [
        {"key": "open_percentage", "integer_value": 70},
        {"key": "open_state", "enum_value": "opened"},
    ],
    "attributes": [],
}

# Ворота полностью закрыты.
MOCK_GATE = {
    "id": "gate_1",
    "serial_number": "SN_GATE_001",
    "name": {"name": "Test Gate"},
    "image_set_type": "gate",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-GATE"},
    "desired_state": [],
    "reported_state": [
        {"key": "open_percentage", "integer_value": 0},
        {"key": "open_state", "enum_value": "closed"},
    ],
    "attributes": [],
}

# Штора в движении (opening).
MOCK_CURTAIN_OPENING = {
    "id": "curtain_moving_1",
    "serial_number": "SN_CURTAIN_002",
    "name": {"name": "Test Moving Curtain"},
    "image_set_type": "curtain",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-CURTAIN"},
    "desired_state": [],
    "reported_state": [
        {"key": "open_percentage", "integer_value": 30},
        {"key": "open_state", "enum_value": "opening"},
    ],
    "attributes": [],
}

# Не-cover устройство — не должно попасть в платформу.
MOCK_FAN_DEVICE = {
    "id": "fan_x_1",
    "serial_number": "SN_FAN_X",
    "name": {"name": "Not A Cover"},
    "image_set_type": "hvac_fan",
    "sw_version": "1.0.0",
    "device_info": {"manufacturer": "Sber", "model": "SBDV-FAN"},
    "desired_state": [],
    "reported_state": [{"key": "on_off", "bool_value": True}],
    "attributes": [],
}


def _make_coordinator(raw_devices: dict) -> MagicMock:
    """Coordinator-mock: devices/entities кэши + StateCache + AsyncMock send."""
    coord = MagicMock()
    coord.data = raw_devices
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    cache = StateCache()
    cache.update_from_devices(coord.devices)
    coord.state_cache = cache
    coord.async_send_device_state = AsyncMock()
    return coord


def _cover_entity(coord: MagicMock, device_id: str) -> SberSbermapCover:
    """Построить SberSbermapCover из primary COVER entity устройства."""
    ent = next(e for e in coord.entities[device_id] if e.platform is Platform.COVER)
    return SberSbermapCover(coord, device_id, ent)


class TestAsyncSetupEntry:
    async def test_creates_entities_only_for_cover_platform(self):
        """Curtain + gate → 2 covers, hvac_fan пропускается."""
        coord = _make_coordinator(
            {"curtain_1": MOCK_CURTAIN, "gate_1": MOCK_GATE, "fan_x_1": MOCK_FAN_DEVICE}
        )
        entry = MagicMock()
        entry.runtime_data = coord
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        assert len(captured) == 2
        assert all(isinstance(e, SberSbermapCover) for e in captured)
        assert {e._device_id for e in captured} == {"curtain_1", "gate_1"}


class TestCurtainEntity:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"curtain_1": MOCK_CURTAIN})

    @pytest.fixture
    def entity(self, coord):
        return _cover_entity(coord, "curtain_1")

    def test_unique_id(self, entity):
        assert entity._attr_unique_id == "curtain_1"

    def test_device_class_curtain(self, entity):
        assert entity._attr_device_class is CoverDeviceClass.CURTAIN

    def test_supported_features_full_set(self, entity):
        features = entity._attr_supported_features
        assert features & CoverEntityFeature.OPEN
        assert features & CoverEntityFeature.CLOSE
        assert features & CoverEntityFeature.SET_POSITION
        assert features & CoverEntityFeature.STOP

    def test_current_cover_position(self, entity):
        assert entity.current_cover_position == 70

    def test_is_closed_false_when_opened(self, entity):
        assert entity.is_closed is False

    def test_not_opening_and_not_closing(self, entity):
        assert entity.is_opening is False
        assert entity.is_closing is False


class TestGateEntity:
    @pytest.fixture
    def entity(self):
        coord = _make_coordinator({"gate_1": MOCK_GATE})
        return _cover_entity(coord, "gate_1")

    def test_device_class_gate(self, entity):
        assert entity._attr_device_class is CoverDeviceClass.GATE

    def test_is_closed_true(self, entity):
        assert entity.is_closed is True

    def test_current_cover_position_zero(self, entity):
        assert entity.current_cover_position == 0


class TestOpeningState:
    def test_is_opening_true_while_moving(self):
        """open_state=opening → is_opening=True, is_closed=False."""
        coord = _make_coordinator({"curtain_moving_1": MOCK_CURTAIN_OPENING})
        entity = _cover_entity(coord, "curtain_moving_1")
        assert entity.is_opening is True
        assert entity.is_closing is False
        assert entity.is_closed is False


class TestUnknownState:
    def test_is_closed_none_for_unrecognized_state(self):
        """State вне множества OPEN/CLOSED/OPENING/CLOSING → is_closed=None."""
        coord = _make_coordinator({"curtain_1": MOCK_CURTAIN})
        ha_entity = HaEntityData(
            platform=Platform.COVER,
            unique_id="curtain_1",
            name="Weird Curtain",
            state="stopped",
            sber_category="curtain",
        )
        # Подменяем кэш entities: is_closed читает state оттуда, не из ctor.
        coord.entities["curtain_1"] = [ha_entity]
        entity = SberSbermapCover(coord, "curtain_1", ha_entity)
        assert entity.is_closed is None


class TestValveFeatures:
    def test_valve_has_no_position_and_stop(self):
        """Категория valve — только OPEN/CLOSE, без SET_POSITION/STOP."""
        coord = _make_coordinator({"curtain_1": MOCK_CURTAIN})
        ha_entity = HaEntityData(
            platform=Platform.COVER,
            unique_id="curtain_1",
            name="Valve",
            state=CoverState.CLOSED,
            sber_category="valve",
        )
        entity = SberSbermapCover(coord, "curtain_1", ha_entity)
        features = entity._attr_supported_features
        assert features & CoverEntityFeature.OPEN
        assert features & CoverEntityFeature.CLOSE
        assert not features & CoverEntityFeature.SET_POSITION
        assert not features & CoverEntityFeature.STOP


class TestMissingEntity:
    """HaEntityData пропала из coordinator.entities — graceful None."""

    @pytest.fixture
    def entity(self):
        coord = _make_coordinator({"curtain_1": MOCK_CURTAIN})
        ent = _cover_entity(coord, "curtain_1")
        coord.entities["curtain_1"] = []
        return ent

    def test_position_is_none(self, entity):
        assert entity.current_cover_position is None

    def test_is_closed_is_none(self, entity):
        assert entity.is_closed is None


class TestCommands:
    @pytest.fixture
    def coord(self):
        return _make_coordinator({"curtain_1": MOCK_CURTAIN})

    @pytest.fixture
    def entity(self, coord):
        return _cover_entity(coord, "curtain_1")

    async def test_open_cover(self, coord, entity):
        await entity.async_open_cover()
        coord.async_send_device_state.assert_awaited_once_with(
            "curtain_1", [AttributeValueDto.of_int("open_set", 100)]
        )

    async def test_close_cover(self, coord, entity):
        await entity.async_close_cover()
        coord.async_send_device_state.assert_awaited_once_with(
            "curtain_1", [AttributeValueDto.of_int("open_set", 0)]
        )

    async def test_set_cover_position(self, coord, entity):
        await entity.async_set_cover_position(position=42)
        coord.async_send_device_state.assert_awaited_once_with(
            "curtain_1", [AttributeValueDto.of_int("open_set", 42)]
        )

    async def test_stop_cover(self, coord, entity):
        await entity.async_stop_cover()
        coord.async_send_device_state.assert_awaited_once_with(
            "curtain_1", [AttributeValueDto.of_enum("open_state", "stop")]
        )
