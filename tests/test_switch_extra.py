"""Tests for SberHome extra switches — sbermap-driven (PR #4 + PR #9).

Extra-переключатели поверх primary on_off: child_lock (чайник/розетка/пылесос),
switch_led (мастер-питание LED-ленты), alarm_mute (датчики газа/дыма).
Генерируются sbermap только когда ключ присутствует в reported_state.
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.sberhome.aiosber.dto import AttributeValueType
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.switch import SberSbermapSwitch

from .conftest import (
    MOCK_DEVICE_KETTLE,
    MOCK_DEVICE_LEDSTRIP,
    MOCK_DEVICE_SENSOR_GAS,
    build_coordinator_caches,
)


def _raw_with_reported(base: dict, key: str, value: bool) -> dict:
    """Копия mock-девайса с добавленным bool-ключом в reported_state."""
    raw = copy.deepcopy(base)
    raw["reported_state"].append({"key": key, "bool_value": value})
    return raw


def _coord_with_raw(raw_devices: dict[str, dict]) -> MagicMock:
    """Coordinator-mock: DTO + sbermap entities + StateCache из raw-словарей."""
    coord = MagicMock()
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    cache = StateCache()
    cache.update_from_devices(coord.devices)
    coord.state_cache = cache
    coord.async_send_device_state = AsyncMock()
    return coord


def _extra_switch(coord, device_id: str, unique_id: str) -> SberSbermapSwitch:
    """Helper: построить SberSbermapSwitch для extra-ключа по unique_id."""
    ent = next(e for e in coord.entities[device_id] if e.unique_id == unique_id)
    return SberSbermapSwitch(coord, device_id, ent)


class TestChildLockSwitch:
    @pytest.fixture
    def coord(self) -> MagicMock:
        raw = _raw_with_reported(MOCK_DEVICE_KETTLE, "child_lock", True)
        return _coord_with_raw({"device_kettle_1": raw})

    @pytest.fixture
    def entity(self, coord) -> SberSbermapSwitch:
        return _extra_switch(coord, "device_kettle_1", "device_kettle_1_child_lock")

    def test_unique_id_has_suffix(self, entity):
        """unique_id extra-switch = <device_id>_<feature_key>."""
        assert entity.unique_id == "device_kettle_1_child_lock"

    def test_entity_category_config(self, entity):
        """child_lock — конфигурационный switch, не primary control."""
        assert entity.entity_category is EntityCategory.CONFIG

    def test_icon(self, entity):
        """Иконка замка из FeatureSpec."""
        assert entity.icon == "mdi:lock"

    def test_is_on(self, entity):
        """child_lock=true в reported_state → is_on True."""
        assert entity.is_on is True

    @pytest.mark.asyncio
    async def test_turn_on_sends_child_lock_key(self, coord, entity):
        """turn_on шлёт именно child_lock, а не primary on_off."""
        await entity.async_turn_on()
        device_id, attrs = coord.async_send_device_state.await_args.args
        assert device_id == "device_kettle_1"
        assert len(attrs) == 1
        assert attrs[0].key == "child_lock"
        assert attrs[0].type is AttributeValueType.BOOL
        assert attrs[0].bool_value is True

    @pytest.mark.asyncio
    async def test_turn_off_sends_child_lock_false(self, coord, entity):
        """turn_off → child_lock=false."""
        await entity.async_turn_off()
        _, attrs = coord.async_send_device_state.await_args.args
        assert attrs[0].key == "child_lock"
        assert attrs[0].bool_value is False


class TestSwitchLedMaster:
    """switch_led — мастер-выключатель контроллера LED-ленты (standby)."""

    @pytest.fixture
    def coord(self) -> MagicMock:
        raw = _raw_with_reported(MOCK_DEVICE_LEDSTRIP, "switch_led", False)
        return _coord_with_raw({"device_ledstrip_1": raw})

    @pytest.fixture
    def entity(self, coord) -> SberSbermapSwitch:
        return _extra_switch(coord, "device_ledstrip_1", "device_ledstrip_1_switch_led")

    def test_is_off_in_standby(self, entity):
        """switch_led=false (standby) → is_on False."""
        assert entity.is_on is False

    def test_config_category_and_icon(self, entity):
        """Config-категория + иконка питания."""
        assert entity.entity_category is EntityCategory.CONFIG
        assert entity.icon == "mdi:power"

    @pytest.mark.asyncio
    async def test_turn_on_sends_switch_led_key(self, coord, entity):
        """turn_on шлёт switch_led=true (питание контроллера), не on_off."""
        await entity.async_turn_on()
        _, attrs = coord.async_send_device_state.await_args.args
        assert attrs[0].key == "switch_led"
        assert attrs[0].bool_value is True


class TestAlarmMuteSwitch:
    """alarm_mute — беззвучный режим датчика газа."""

    @pytest.fixture
    def coord(self) -> MagicMock:
        raw = _raw_with_reported(MOCK_DEVICE_SENSOR_GAS, "alarm_mute", False)
        return _coord_with_raw({"device_gas_1": raw})

    @pytest.fixture
    def entity(self, coord) -> SberSbermapSwitch:
        return _extra_switch(coord, "device_gas_1", "device_gas_1_alarm_mute")

    def test_is_off(self, entity):
        """alarm_mute=false → is_on False."""
        assert entity.is_on is False

    def test_icon(self, entity):
        """Иконка отключенного звонка из FeatureSpec."""
        assert entity.icon == "mdi:bell-off"

    @pytest.mark.asyncio
    async def test_turn_on_sends_alarm_mute_key(self, coord, entity):
        """turn_on шлёт alarm_mute=true."""
        await entity.async_turn_on()
        device_id, attrs = coord.async_send_device_state.await_args.args
        assert device_id == "device_gas_1"
        assert attrs[0].key == "alarm_mute"
        assert attrs[0].bool_value is True
