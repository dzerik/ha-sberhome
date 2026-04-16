"""Tests for SberHome fan platform — sbermap-driven (PR #6)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.components.fan import FanEntityFeature

from custom_components.sberhome.fan import SberSbermapFan, async_setup_entry
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


def _fan(coordinator, device_id: str) -> SberSbermapFan:
    ent = next(
        e for e in coordinator.entities[device_id] if e.unique_id == device_id
    )
    return SberSbermapFan(coordinator, device_id, ent)


class TestHvacFan:
    @pytest.fixture
    def fan(self, coordinator):
        return _fan(coordinator, "device_hvac_fan_1")

    def test_unique_id(self, fan):
        assert fan._attr_unique_id == "device_hvac_fan_1"

    def test_supported_features(self, fan):
        sf = fan._attr_supported_features
        assert sf & FanEntityFeature.TURN_ON
        assert sf & FanEntityFeature.PRESET_MODE

    def test_preset_modes(self, fan):
        assert fan._attr_preset_modes == ["low", "medium", "high", "turbo"]

    def test_is_on_true(self, fan):
        assert fan.is_on is True

    def test_preset_mode(self, fan):
        assert fan.preset_mode == "medium"

    @pytest.mark.asyncio
    async def test_set_preset_mode(self, fan, coordinator):
        await fan.async_set_preset_mode("high")
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "hvac_air_flow_power" and a.enum_value == "high" for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_on_with_preset(self, fan, coordinator):
        await fan.async_turn_on(preset_mode="turbo")
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is True for a in attrs)
        assert any(a.key == "hvac_air_flow_power" and a.enum_value == "turbo" for a in attrs)

    @pytest.mark.asyncio
    async def test_turn_off(self, fan, coordinator):
        await fan.async_turn_off()
        attrs = coordinator._fake_client.devices.set_state.call_args.args[1]
        assert any(a.key == "on_off" and a.bool_value is False for a in attrs)


class TestAirPurifier:
    """Air Purifier preset_modes включают 'auto'."""

    @pytest.fixture
    def purifier(self, coordinator):
        return _fan(coordinator, "device_hvac_purifier_1")

    def test_preset_modes_include_auto(self, purifier):
        assert "auto" in purifier._attr_preset_modes


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_fan_entities(self, coordinator):
        entry = MagicMock()
        entry.runtime_data = coordinator
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)
        ids = {e._device_id for e in captured}
        assert "device_hvac_fan_1" in ids
        assert "device_hvac_purifier_1" in ids
