"""Tests for SberHome humidifier platform — sbermap-driven (PR #6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.humidifier import HumidifierEntityFeature

from custom_components.sberhome.humidifier import (
    SberSbermapHumidifier,
    async_setup_entry,
)
from tests.conftest import build_coordinator_caches


@pytest.fixture
def coordinator(mock_devices_extra):
    coord = MagicMock()
    coord.data = mock_devices_extra
    coord.devices, coord.entities = build_coordinator_caches(mock_devices_extra)
    coord.home_api = AsyncMock()
    coord.home_api.get_cached_devices = MagicMock(return_value=mock_devices_extra)
    fake_client = AsyncMock()
    fake_client.devices = AsyncMock()
    coord.home_api.get_sber_client = AsyncMock(return_value=fake_client)
    coord._fake_client = fake_client
    coord.async_set_updated_data = MagicMock()
    coord._rebuild_dto_caches = MagicMock()
    return coord


@pytest.fixture
def humidifier(coordinator):
    ent = next(
        e for e in coordinator.entities["device_humidifier_1"]
        if e.unique_id == "device_humidifier_1"
    )
    return SberSbermapHumidifier(coordinator, "device_humidifier_1", ent)


class TestHumidifier:
    def test_unique_id(self, humidifier):
        assert humidifier._attr_unique_id == "device_humidifier_1"

    def test_min_max_humidity(self, humidifier):
        assert humidifier._attr_min_humidity == 30
        assert humidifier._attr_max_humidity == 80

    def test_supported_features_modes(self, humidifier):
        assert humidifier._attr_supported_features & HumidifierEntityFeature.MODES

    def test_available_modes(self, humidifier):
        assert humidifier._attr_available_modes == ["auto", "low", "medium", "high", "turbo"]

    def test_is_on_true(self, humidifier):
        assert humidifier.is_on is True

    def test_target_humidity(self, humidifier):
        assert humidifier.target_humidity == 55

    def test_mode(self, humidifier):
        assert humidifier.mode == "medium"

    @pytest.mark.asyncio
    async def test_set_humidity(self, humidifier, coordinator):
        await humidifier.async_set_humidity(60)
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "hvac_humidity_set" and a.integer_value == 60 for a in attrs)

    @pytest.mark.asyncio
    async def test_set_mode(self, humidifier, coordinator):
        await humidifier.async_set_mode("turbo")
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "hvac_air_flow_power" and a.enum_value == "turbo" for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_on(self, humidifier, coordinator):
        await humidifier.async_turn_on()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is True for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_off(self, humidifier, coordinator):
        await humidifier.async_turn_off()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is False for a in attrs)


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_humidifier(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._device_id for e in captured}
        assert "device_humidifier_1" in ids
