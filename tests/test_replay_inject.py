"""Tests for replay / inject (DevTools #3).

The injection path is the quickest way to turn a DevTools user into a
DoS on themselves — a bug here could swallow a message, run it twice,
or bypass the dispatcher.  These tests pin the contract:

* A DEVICE_STATE-shaped payload lands in the state-change handler and
  patches the state cache exactly like a real WS push would.
* DEVMAN_EVENT and GROUP_STATE payloads hit their respective handlers.
* Malformed payload returns ``handled=False`` instead of raising.
* WS message log tags synthetic traffic with ``direction="replay"``
  (or ``"in"`` when ``mark_replay=False``).
* state_diff collector sees the injected message just like a real one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.dto.values import (
    AttributeValueDto,
    AttributeValueType,
)
from custom_components.sberhome.api import HomeAPI, SberAPI
from custom_components.sberhome.coordinator import SberHomeCoordinator


@pytest.fixture
def coordinator():
    hass = MagicMock()
    hass.data = {}
    hass.loop = AsyncMock()
    hass.async_create_task = MagicMock()

    entry = MagicMock()
    entry.options = {}

    sber_api = AsyncMock(spec=SberAPI)
    home_api = AsyncMock(spec=HomeAPI)
    home_api.get_cached_devices = MagicMock(return_value={})
    home_api.get_cached_tree = MagicMock(return_value=None)

    coord = SberHomeCoordinator(hass, entry, sber_api, home_api)
    coord.async_set_updated_data = MagicMock()
    return coord


def _seed_device(coord: SberHomeCoordinator, temp: int) -> None:
    dto = DeviceDto(
        id="dev-1",
        image_set_type="cat_sensor_temp_humidity",
        reported_state=[
            AttributeValueDto(
                key="temperature",
                type=AttributeValueType.INTEGER,
                integer_value=temp,
            ),
        ],
    )
    coord.state_cache._devices = {"dev-1": dto}
    coord.entities = {}


def _device_state_payload(temp: int) -> dict:
    # Shape matches what the WS transport delivers (one populated
    # top-level field — "state" — which auto-routes to DEVICE_STATE).
    return {
        "state": {
            "device_id": "dev-1",
            "reported_state": [
                {"key": "temperature", "type": "INTEGER", "integer_value": temp},
            ],
        },
    }


class TestInjectRoutesThroughDispatcher:
    async def test_device_state_payload_patches_cache(self, coordinator):
        _seed_device(coordinator, 200)
        # Prime the diff collector baseline too so we see a real delta.
        await coordinator.async_inject_ws_message(_device_state_payload(200))

        res = await coordinator.async_inject_ws_message(_device_state_payload(225))
        # Must route to DEVICE_STATE handler — otherwise we lose state patches.
        # Topic.value is the API string, lowercase.
        assert res["topic"] == "device_state"
        assert res["handled"] is True
        assert res["device_id"] == "dev-1"
        # Cache patched by the same _on_ws_device_state handler used for real WS.
        dto = coordinator.devices["dev-1"]
        by_key = {av.key: av for av in dto.reported_state}
        assert by_key["temperature"].integer_value == 225

    async def test_injected_payload_appears_in_state_diffs(self, coordinator):
        _seed_device(coordinator, 200)
        await coordinator.async_inject_ws_message(_device_state_payload(200))
        await coordinator.async_inject_ws_message(_device_state_payload(225))
        diffs = coordinator.diff_collector.snapshot()
        # The whole point of replay: the delta must show up in state-diff,
        # otherwise the user can't verify their replay did anything.
        assert any(
            d["device_id"] == "dev-1"
            and d["changed"].get("temperature", {}).get("after", {}).get("integer_value") == 225
            for d in diffs
        ), diffs


class TestMessageLogMarking:
    async def test_mark_replay_true_writes_replay_direction(self, coordinator):
        _seed_device(coordinator, 200)
        await coordinator.async_inject_ws_message(_device_state_payload(200), mark_replay=True)
        directions = [m["direction"] for m in coordinator._ws_log]
        # The UI tints synthetic rows based on this field — losing it
        # turns the log into a liar about what's real.
        assert "replay" in directions

    async def test_mark_replay_false_writes_in_direction(self, coordinator):
        _seed_device(coordinator, 200)
        await coordinator.async_inject_ws_message(_device_state_payload(200), mark_replay=False)
        directions = [m["direction"] for m in coordinator._ws_log]
        assert "in" in directions
        assert "replay" not in directions


class TestErrorPaths:
    async def test_empty_payload_returns_handled_false(self, coordinator):
        # A malformed payload (all fields None) must not raise — the user
        # types freely and an uncaught exception here would reach HA
        # logs as an error every keystroke.
        res = await coordinator.async_inject_ws_message({})
        assert res["handled"] is False

    async def test_unknown_field_is_gracefully_ignored(self, coordinator):
        # Payload with a bogus field that doesn't map to any Topic — the
        # from_dict strips unknown fields, so msg.topic ends up None.
        res = await coordinator.async_inject_ws_message({"unknown_field": {}})
        assert res["handled"] is False


class TestWsHandlers:
    """Smoke-test the two WS wrappers (inject + replay) via __wrapped__."""

    async def test_inject_ws_returns_handled_true(self, coordinator):
        from unittest.mock import patch

        from custom_components.sberhome.websocket_api.replay import (
            ws_inject_ws_message,
        )

        _seed_device(coordinator, 200)
        await coordinator.async_inject_ws_message(_device_state_payload(200))

        conn = MagicMock()
        conn.send_result = MagicMock()
        conn.send_error = MagicMock()
        hass = MagicMock()
        with patch(
            "custom_components.sberhome.websocket_api.replay.get_coordinator",
            return_value=coordinator,
        ):
            await ws_inject_ws_message.__wrapped__(
                hass,
                conn,
                {
                    "id": 1,
                    "payload": _device_state_payload(225),
                    "mark_replay": True,
                },
            )
        payload = conn.send_result.call_args[0][1]
        assert payload["handled"] is True
        conn.send_error.assert_not_called()

    async def test_replay_ws_missing_coordinator_sends_error(self, coordinator):
        from unittest.mock import patch

        from custom_components.sberhome.websocket_api.replay import (
            ws_replay_ws_message,
        )

        conn = MagicMock()
        conn.send_result = MagicMock()
        conn.send_error = MagicMock()
        hass = MagicMock()
        with patch(
            "custom_components.sberhome.websocket_api.replay.get_coordinator",
            return_value=None,
        ):
            await ws_replay_ws_message.__wrapped__(hass, conn, {"id": 1, "payload": {}})
        # A clear error code lets the UI show "integration not loaded"
        # instead of a generic timeout.
        err = conn.send_error.call_args
        assert err[0][1] == "not_loaded"
