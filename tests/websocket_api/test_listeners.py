"""Tests for sberhome/listeners/list WS endpoint."""

from unittest.mock import MagicMock

import pytest

from custom_components.sberhome.listeners import (
    ListenerFilter,
    ListenerRegistry,
    ListenerSpec,
)
from custom_components.sberhome.websocket_api.listeners import (
    ws_list_listeners,
)


@pytest.mark.asyncio
async def test_ws_list_listeners_returns_specs():
    """Endpoint возвращает все listener-specs."""
    spec = ListenerSpec(
        slug="any_time",
        name="Any TIME",
        filter=ListenerFilter(trigger_types=frozenset({"TIME"})),
        description="по расписанию",
    )
    spec.last_fired_at = "2026-05-13T08:00:00+00:00"

    coord = MagicMock()
    coord.listener_registry = ListenerRegistry([spec])

    hass = MagicMock()
    hass.data = {"sberhome": {}}
    entry = MagicMock()
    entry.runtime_data = coord
    hass.config_entries.async_entries.return_value = [entry]

    connection = MagicMock()

    await ws_list_listeners.__wrapped__(
        hass, connection, {"id": 1, "type": "sberhome/listeners/list"}
    )

    connection.send_result.assert_called_once()
    call_args = connection.send_result.call_args
    msg_id, result = call_args.args[0], call_args.args[1]
    assert msg_id == 1
    assert len(result["listeners"]) == 1
    listener_payload = result["listeners"][0]
    assert listener_payload["slug"] == "any_time"
    assert listener_payload["enabled"] is True
    assert listener_payload["last_fired_at"] == "2026-05-13T08:00:00+00:00"
    assert listener_payload["filter"]["trigger_types"] == ["TIME"]


@pytest.mark.asyncio
async def test_ws_list_listeners_empty():
    coord = MagicMock()
    coord.listener_registry = ListenerRegistry([])

    hass = MagicMock()
    hass.data = {"sberhome": {}}
    entry = MagicMock()
    entry.runtime_data = coord
    hass.config_entries.async_entries.return_value = [entry]

    connection = MagicMock()
    await ws_list_listeners.__wrapped__(
        hass, connection, {"id": 2, "type": "sberhome/listeners/list"}
    )
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args.args[1]
    assert result["listeners"] == []


@pytest.mark.asyncio
async def test_ws_list_listeners_no_entry_returns_empty():
    """Integration ещё не настроена (нет entries) → пустой list."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_entries.return_value = []

    connection = MagicMock()
    await ws_list_listeners.__wrapped__(
        hass, connection, {"id": 3, "type": "sberhome/listeners/list"}
    )
    connection.send_result.assert_called_once()
    result = connection.send_result.call_args.args[1]
    assert result["listeners"] == []
