"""Tests для SberClient facade на coordinator.

Архитектурный долг (CLAUDE.md, парадигма пункт 6) закрыт частично:
HomeAPI остался как HA-shim, но все новые API-доступы идут через
`coordinator.client.<domain>` — единая точка входа.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.sberhome.aiosber import SberClient
from custom_components.sberhome.aiosber.api import (
    DeviceAPI,
    GroupAPI,
    IndicatorAPI,
    InventoryAPI,
    PairingAPI,
    ScenarioAPI,
)
from custom_components.sberhome.coordinator import SberHomeCoordinator


def _stub_coord() -> MagicMock:
    coord = MagicMock(spec=SberHomeCoordinator)
    coord.home_api = MagicMock()
    coord.home_api._transport = MagicMock()
    coord._client = None
    return coord


class TestCoordinatorClientFacade:
    def test_client_lazily_built(self):
        coord = _stub_coord()
        client = SberHomeCoordinator.client.fget(coord)
        assert isinstance(client, SberClient)
        # Reuse: повторный доступ возвращает тот же instance.
        assert SberHomeCoordinator.client.fget(coord) is client

    def test_client_exposes_all_domains(self):
        coord = _stub_coord()
        client = SberHomeCoordinator.client.fget(coord)
        assert isinstance(client.devices, DeviceAPI)
        assert isinstance(client.groups, GroupAPI)
        assert isinstance(client.scenarios, ScenarioAPI)
        assert isinstance(client.pairing, PairingAPI)
        assert isinstance(client.indicator, IndicatorAPI)
        assert isinstance(client.inventory, InventoryAPI)

    def test_internal_factories_route_through_client(self):
        coord = _stub_coord()
        # Все 4 internal API factories должны возвращать тот же instance,
        # что и client.<domain> — без лишних new()-вызовов.
        client = SberHomeCoordinator.client.fget(coord)
        # Закрепляем client на mock, чтобы attribute access shadow'нул спек.
        coord.client = client
        assert SberHomeCoordinator._scenario_api(coord) is client.scenarios
        assert SberHomeCoordinator._inventory_api(coord) is client.inventory
        assert SberHomeCoordinator._device_api(coord) is client.devices
        assert SberHomeCoordinator._indicator_api(coord) is client.indicator
