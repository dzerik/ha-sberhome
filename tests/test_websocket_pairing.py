"""Tests для pairing WS endpoints (PairingAPI shims)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sberhome.websocket_api.pairing import (
    ws_get_wifi_credentials,
    ws_list_matter_categories,
    ws_matter_attestation,
    ws_matter_complete,
    ws_matter_connect_controller,
    ws_matter_connect_device,
    ws_matter_noc,
    ws_start_pairing,
)


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture
def hass():
    return MagicMock()


def _coord_with_api(api: MagicMock) -> MagicMock:
    coord = MagicMock()
    coord.client = MagicMock()
    coord.client.pairing = api
    return coord


def _patches(coord: MagicMock, api: MagicMock):
    return (
        patch(
            "custom_components.sberhome.websocket_api.pairing.get_coordinator",
            return_value=coord,
        ),
        patch(
            "custom_components.sberhome.websocket_api.pairing.get_coordinator",
            return_value=coord,
        ),
    )


# ---------------------------------------------------------------------------
# wifi_credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wifi_credentials_passes_through(hass, connection):
    api = MagicMock()
    api.get_wifi_credentials = AsyncMock(return_value={"ssid": "Sber-Setup", "password": "x"})
    coord = _coord_with_api(api)
    p1, p2 = _patches(coord, api)
    with p1, p2:
        await ws_get_wifi_credentials.__wrapped__(hass, connection, {"id": 1})
    assert connection.send_result.call_args[0][1] == {"ssid": "Sber-Setup", "password": "x"}


@pytest.mark.asyncio
async def test_wifi_credentials_when_no_coordinator(hass, connection):
    with patch(
        "custom_components.sberhome.websocket_api.pairing.get_coordinator",
        return_value=None,
    ):
        await ws_get_wifi_credentials.__wrapped__(hass, connection, {"id": 1})
    assert connection.send_error.call_args[0][1] == "not_loaded"


@pytest.mark.asyncio
async def test_wifi_credentials_surfaces_api_error(hass, connection):
    api = MagicMock()
    api.get_wifi_credentials = AsyncMock(side_effect=RuntimeError("boom"))
    coord = _coord_with_api(api)
    p1, p2 = _patches(coord, api)
    with p1, p2:
        await ws_get_wifi_credentials.__wrapped__(hass, connection, {"id": 1})
    assert connection.send_error.call_args[0][1] == "fetch_failed"


# ---------------------------------------------------------------------------
# matter_categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_matter_categories_wraps_payload(hass, connection):
    api = MagicMock()
    api.list_matter_categories = AsyncMock(return_value=[{"id": "light"}, {"id": "lock"}])
    coord = _coord_with_api(api)
    p1, p2 = _patches(coord, api)
    with p1, p2:
        await ws_list_matter_categories.__wrapped__(hass, connection, {"id": 2})
    assert connection.send_result.call_args[0][1] == {
        "categories": [{"id": "light"}, {"id": "lock"}]
    }


# ---------------------------------------------------------------------------
# start_pairing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_start_pairing_passes_body(hass, connection):
    api = MagicMock()
    api.start_pairing = AsyncMock(return_value={"pairing_id": "p-1"})
    coord = _coord_with_api(api)
    p1, p2 = _patches(coord, api)
    with p1, p2:
        await ws_start_pairing.__wrapped__(
            hass,
            connection,
            {
                "id": 3,
                "pairing_type": "wifi",
                "image_set_type": "dt_bulb_e27_m",
                "timeout": 60,
            },
        )
    body = api.start_pairing.await_args[0][0]
    assert body.pairing_type == "wifi"
    assert body.image_set_type == "dt_bulb_e27_m"
    assert body.timeout == 60
    assert connection.send_result.call_args[0][1] == {"pairing_id": "p-1"}


@pytest.mark.asyncio
async def test_start_pairing_surfaces_error(hass, connection):
    api = MagicMock()
    api.start_pairing = AsyncMock(side_effect=RuntimeError("conflict"))
    coord = _coord_with_api(api)
    p1, p2 = _patches(coord, api)
    with p1, p2:
        await ws_start_pairing.__wrapped__(hass, connection, {"id": 4, "pairing_type": "matter"})
    assert connection.send_error.call_args[0][1] == "pairing_failed"


# ---------------------------------------------------------------------------
# matter_* steps — параметризовано, все 5 одинаково обёрнуты
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ws_cmd,api_method",
    [
        (ws_matter_attestation, "matter_attestation"),
        (ws_matter_noc, "matter_request_noc"),
        (ws_matter_complete, "matter_complete"),
        (ws_matter_connect_controller, "matter_connect_controller"),
        (ws_matter_connect_device, "matter_connect_device"),
    ],
)
async def test_matter_step_passes_payload(hass, connection, ws_cmd, api_method):
    api = MagicMock()
    setattr(api, api_method, AsyncMock(return_value={"ok": True}))
    coord = _coord_with_api(api)
    p1, p2 = _patches(coord, api)
    with p1, p2:
        await ws_cmd.__wrapped__(hass, connection, {"id": 5, "payload": {"node_id": "x"}})
    getattr(api, api_method).assert_awaited_once_with({"node_id": "x"})
    assert connection.send_result.call_args[0][1] == {"ok": True}


@pytest.mark.asyncio
async def test_matter_step_uses_empty_payload_default(hass, connection):
    """Когда payload не передан — отправляем пустой dict (не None)."""
    api = MagicMock()
    api.matter_attestation = AsyncMock(return_value={})
    coord = _coord_with_api(api)
    p1, p2 = _patches(coord, api)
    with p1, p2:
        await ws_matter_attestation.__wrapped__(hass, connection, {"id": 6})
    api.matter_attestation.assert_awaited_once_with({})
