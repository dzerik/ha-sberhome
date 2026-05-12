"""Tests for sberhome/get_homes + multi-home filter в sberhome/get_rooms.

См. issue #2 — multi-home UI filter.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sberhome.aiosber.dto import DeviceDto
from custom_components.sberhome.aiosber.dto.union import (
    UnionDto,
    UnionTreeDto,
    UnionType,
)
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.websocket_api.rooms import ws_get_homes, ws_get_rooms


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture
def hass():
    return MagicMock()


def _multi_home_cache() -> StateCache:
    """StateCache с 2 HOME-узлами для тестов."""
    cache = StateCache()
    tree = UnionTreeDto(
        union=None,
        devices=[],
        children=[
            UnionTreeDto(
                union=UnionDto(id="home-main", name="Мой дом", group_type=UnionType.HOME),
                devices=[],
                children=[
                    UnionTreeDto(
                        union=UnionDto(id="room-kitchen", name="Кухня", group_type=UnionType.ROOM),
                        devices=[
                            DeviceDto(id="dev-1", name="Лампа"),
                            DeviceDto(id="dev-2", name="Розетка"),
                        ],
                        children=[],
                    ),
                ],
            ),
            UnionTreeDto(
                union=UnionDto(id="home-dacha", name="Дача", group_type=UnionType.HOME),
                devices=[],
                children=[
                    UnionTreeDto(
                        union=UnionDto(
                            id="room-veranda", name="Веранда", group_type=UnionType.ROOM
                        ),
                        devices=[DeviceDto(id="dev-3", name="Лента")],
                        children=[],
                    ),
                ],
            ),
        ],
    )
    cache.update_from_tree(tree)
    return cache


def _coord_with_cache(cache: StateCache) -> MagicMock:
    coord = MagicMock()
    coord.state_cache = cache
    return coord


# ---------------------------------------------------------------------------
# sberhome/get_homes
# ---------------------------------------------------------------------------


class TestGetHomes:
    def test_returns_all_homes_with_metadata(self, hass, connection):
        coord = _coord_with_cache(_multi_home_cache())
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            ws_get_homes(hass, connection, {"id": 1, "type": "sberhome/get_homes"})
        result = connection.send_result.call_args[0][1]
        assert len(result["homes"]) == 2
        names = {h["name"] for h in result["homes"]}
        assert names == {"Мой дом", "Дача"}

    def test_marks_first_home_as_default(self, hass, connection):
        coord = _coord_with_cache(_multi_home_cache())
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            ws_get_homes(hass, connection, {"id": 2, "type": "sberhome/get_homes"})
        result = connection.send_result.call_args[0][1]
        defaults = [h for h in result["homes"] if h["is_default"]]
        assert len(defaults) == 1
        assert defaults[0]["id"] == "home-main"

    def test_includes_room_and_device_counts(self, hass, connection):
        coord = _coord_with_cache(_multi_home_cache())
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            ws_get_homes(hass, connection, {"id": 3, "type": "sberhome/get_homes"})
        result = connection.send_result.call_args[0][1]
        by_id = {h["id"]: h for h in result["homes"]}
        assert by_id["home-main"]["device_count"] == 2
        assert by_id["home-main"]["room_count"] == 1
        assert by_id["home-dacha"]["device_count"] == 1
        assert by_id["home-dacha"]["room_count"] == 1

    def test_empty_cache_returns_empty_list(self, hass, connection):
        coord = _coord_with_cache(StateCache())
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            ws_get_homes(hass, connection, {"id": 4, "type": "sberhome/get_homes"})
        result = connection.send_result.call_args[0][1]
        assert result == {"homes": []}

    def test_returns_error_when_no_coordinator(self, hass, connection):
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=None,
        ):
            ws_get_homes(hass, connection, {"id": 5, "type": "sberhome/get_homes"})
        connection.send_error.assert_called_once()
        assert connection.send_error.call_args[0][1] == "not_loaded"


# ---------------------------------------------------------------------------
# sberhome/get_rooms with home_id filter
# ---------------------------------------------------------------------------


class TestGetRoomsWithHomeFilter:
    def test_without_home_id_returns_all_rooms_legacy(self, hass, connection):
        """BC: без home_id — все rooms всех домов, total = все устройства."""
        coord = _coord_with_cache(_multi_home_cache())
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            ws_get_rooms(hass, connection, {"id": 1, "type": "sberhome/get_rooms"})
        result = connection.send_result.call_args[0][1]
        assert {r["name"] for r in result["rooms"]} == {"Кухня", "Веранда"}
        assert result["total_devices"] == 3
        # home → первый (legacy)
        assert result["home"]["id"] == "home-main"

    def test_with_home_id_filters_rooms_and_totals(self, hass, connection):
        coord = _coord_with_cache(_multi_home_cache())
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            ws_get_rooms(
                hass,
                connection,
                {"id": 2, "type": "sberhome/get_rooms", "home_id": "home-dacha"},
            )
        result = connection.send_result.call_args[0][1]
        assert {r["name"] for r in result["rooms"]} == {"Веранда"}
        assert result["total_devices"] == 1
        assert result["home"]["id"] == "home-dacha"
        assert result["home"]["name"] == "Дача"

    def test_with_home_id_main(self, hass, connection):
        coord = _coord_with_cache(_multi_home_cache())
        with patch(
            "custom_components.sberhome.websocket_api.rooms.get_coordinator",
            return_value=coord,
        ):
            ws_get_rooms(
                hass,
                connection,
                {"id": 3, "type": "sberhome/get_rooms", "home_id": "home-main"},
            )
        result = connection.send_result.call_args[0][1]
        assert {r["name"] for r in result["rooms"]} == {"Кухня"}
        assert result["total_devices"] == 2
