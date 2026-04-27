"""Tests for enabled-device WS endpoints — unsupported-category guard.

Устройства, для которых `resolve_category` вернул None, не создают ни
одной HA entity. Разрешать их enable — значит молча пускать «пустышки»
в config_entry.options, поэтому WS-endpoints отказывают с явной ошибкой,
которую UI переводит в тост.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.websocket_api.enabled import (
    ws_set_enabled,
    ws_toggle_device,
)


def _coord_with(*devices: tuple[str, str | None]) -> MagicMock:
    """Build coord mock with (device_id, image_set_type) tuples."""
    coord = MagicMock()
    coord.devices = {
        dev_id: DeviceDto(id=dev_id, image_set_type=image_set_type)
        for dev_id, image_set_type in devices
    }
    coord.enabled_device_ids = set()
    coord.async_set_enabled_device_ids = AsyncMock()
    return coord


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture
def hass():
    return MagicMock()


class TestToggleDeviceUnsupported:
    @pytest.mark.asyncio
    async def test_enable_unsupported_rejected(self, hass, connection):
        coord = _coord_with(("dev-bad", "dt_boom_r2_dark_blue_s"))
        with patch(
            "custom_components.sberhome.websocket_api.enabled.get_coordinator",
            return_value=coord,
        ):
            await ws_toggle_device.__wrapped__(
                hass,
                connection,
                {"id": 1, "device_id": "dev-bad", "enabled": True},
            )
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "unsupported_category"
        coord.async_set_enabled_device_ids.assert_not_called()

    @pytest.mark.asyncio
    async def test_enable_supported_allowed(self, hass, connection):
        coord = _coord_with(("dev-light", "dt_bulb_e27_m"))
        with patch(
            "custom_components.sberhome.websocket_api.enabled.get_coordinator",
            return_value=coord,
        ):
            await ws_toggle_device.__wrapped__(
                hass,
                connection,
                {"id": 2, "device_id": "dev-light", "enabled": True},
            )
        connection.send_error.assert_not_called()
        coord.async_set_enabled_device_ids.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disable_unsupported_still_allowed(self, hass, connection):
        """Отключение неподдерживаемого устройства разрешено — legacy cleanup."""
        coord = _coord_with(("dev-bad", "dt_boom_r2_dark_blue_s"))
        coord.enabled_device_ids = {"dev-bad"}
        with patch(
            "custom_components.sberhome.websocket_api.enabled.get_coordinator",
            return_value=coord,
        ):
            await ws_toggle_device.__wrapped__(
                hass,
                connection,
                {"id": 3, "device_id": "dev-bad", "enabled": False},
            )
        connection.send_error.assert_not_called()
        coord.async_set_enabled_device_ids.assert_awaited_once()


class TestSetEnabledUnsupported:
    @pytest.mark.asyncio
    async def test_batch_with_unsupported_rejected(self, hass, connection):
        coord = _coord_with(
            ("dev-light", "dt_bulb_e27_m"),
            ("dev-bad", "dt_boom_r2_dark_blue_s"),
        )
        with patch(
            "custom_components.sberhome.websocket_api.enabled.get_coordinator",
            return_value=coord,
        ):
            await ws_set_enabled.__wrapped__(
                hass,
                connection,
                {"id": 4, "device_ids": ["dev-light", "dev-bad"]},
            )
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "unsupported_category"
        coord.async_set_enabled_device_ids.assert_not_called()

    @pytest.mark.asyncio
    async def test_batch_all_supported_passes(self, hass, connection):
        coord = _coord_with(
            ("dev-light", "dt_bulb_e27_m"),
            ("dev-button", "cat_button_m"),
        )
        with patch(
            "custom_components.sberhome.websocket_api.enabled.get_coordinator",
            return_value=coord,
        ):
            await ws_set_enabled.__wrapped__(
                hass,
                connection,
                {"id": 5, "device_ids": ["dev-light", "dev-button"]},
            )
        connection.send_error.assert_not_called()
        coord.async_set_enabled_device_ids.assert_awaited_once_with(["dev-light", "dev-button"])
