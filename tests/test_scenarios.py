"""Tests для Sber scenarios → HA buttons + at_home binary_sensor/switch.

Покрытие:
- Coordinator throttles scenario poll (SCENARIO_POLL_INTERVAL_SEC).
- Ошибка ScenarioAPI выставляет _scenarios_disabled и не рушит refresh.
- async_execute_scenario / async_set_at_home делают правильные API-вызовы.
- SberScenarioButton press → coordinator.async_execute_scenario.
- SberAtHomeBinarySensor / SberAtHomeSwitch read/write через coordinator.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.binary_sensor import SberAtHomeBinarySensor
from custom_components.sberhome.button import SberScenarioButton
from custom_components.sberhome.coordinator import SCENARIO_POLL_INTERVAL_SEC
from custom_components.sberhome.switch import SberAtHomeSwitch

# ---------------------------------------------------------------------------
# Coordinator scenario polling
# ---------------------------------------------------------------------------


def _coord(scenarios: list | None = None, at_home: bool | None = None) -> MagicMock:
    """Build minimal coord stub for entity-level unit tests."""
    coord = MagicMock()
    coord.scenarios = scenarios or []
    coord.at_home = at_home
    coord.async_execute_scenario = AsyncMock()
    coord.async_set_at_home = AsyncMock()
    return coord


# ---------------------------------------------------------------------------
# SberScenarioButton
# ---------------------------------------------------------------------------


class TestScenarioButton:
    def test_unique_id_and_name(self):
        coord = _coord(scenarios=[ScenarioDto(id="sc-1", name="Welcome home")])
        btn = SberScenarioButton(coord, "sc-1", "Welcome home")
        assert btn._attr_unique_id == "sberhome_scenario_sc-1"
        assert btn._attr_name == "Welcome home"

    def test_available_when_scenario_present(self):
        coord = _coord(scenarios=[ScenarioDto(id="sc-1", name="X")])
        btn = SberScenarioButton(coord, "sc-1", "X")
        assert btn.available is True

    def test_unavailable_when_scenario_removed(self):
        coord = _coord(scenarios=[])
        btn = SberScenarioButton(coord, "sc-1", "X")
        assert btn.available is False

    @pytest.mark.asyncio
    async def test_press_triggers_execute(self):
        coord = _coord(scenarios=[ScenarioDto(id="sc-1", name="X")])
        btn = SberScenarioButton(coord, "sc-1", "X")
        await btn.async_press()
        coord.async_execute_scenario.assert_awaited_once_with("sc-1")


# ---------------------------------------------------------------------------
# at_home binary_sensor
# ---------------------------------------------------------------------------


class TestAtHomeBinarySensor:
    def test_unavailable_when_at_home_is_none(self):
        sensor = SberAtHomeBinarySensor(_coord(at_home=None))
        assert sensor.available is False
        assert sensor.is_on is None

    @pytest.mark.parametrize("value,expected", [(True, True), (False, False)])
    def test_reflects_coordinator_at_home(self, value, expected):
        sensor = SberAtHomeBinarySensor(_coord(at_home=value))
        assert sensor.available is True
        assert sensor.is_on is expected


# ---------------------------------------------------------------------------
# at_home switch
# ---------------------------------------------------------------------------


class TestAtHomeSwitch:
    def test_unavailable_until_first_poll(self):
        sw = SberAtHomeSwitch(_coord(at_home=None))
        assert sw.available is False

    @pytest.mark.parametrize("value", [True, False])
    def test_is_on_mirrors_coordinator(self, value):
        sw = SberAtHomeSwitch(_coord(at_home=value))
        assert sw.is_on is value

    @pytest.mark.asyncio
    async def test_turn_on_calls_coordinator(self):
        coord = _coord(at_home=False)
        sw = SberAtHomeSwitch(coord)
        await sw.async_turn_on()
        coord.async_set_at_home.assert_awaited_once_with(True)

    @pytest.mark.asyncio
    async def test_turn_off_calls_coordinator(self):
        coord = _coord(at_home=True)
        sw = SberAtHomeSwitch(coord)
        await sw.async_turn_off()
        coord.async_set_at_home.assert_awaited_once_with(False)


# ---------------------------------------------------------------------------
# Coordinator.async_execute_scenario / set_at_home
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_coordinator_executes_scenario_via_scenario_api():
    """async_execute_scenario строит ScenarioAPI поверх HomeAPI._transport."""
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    api = MagicMock()
    api.execute_command = AsyncMock()
    coord._scenario_api = MagicMock(return_value=api)

    await SberHomeCoordinator.async_execute_scenario(coord, "sc-42")
    api.execute_command.assert_awaited_once_with({"scenario_id": "sc-42"})


@pytest.mark.asyncio
async def test_coordinator_sets_at_home_optimistically():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord.data = {}
    coord.async_set_updated_data = MagicMock()
    api = MagicMock()
    api.set_at_home = AsyncMock()
    coord._scenario_api = MagicMock(return_value=api)

    await SberHomeCoordinator.async_set_at_home(coord, True)
    api.set_at_home.assert_awaited_once_with(True)
    # Optimistic patch перед следующим poll'ом.
    assert coord.at_home is True
    coord.async_set_updated_data.assert_called_once()


# ---------------------------------------------------------------------------
# Throttling and disabled flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_poll_skips_when_disabled():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._scenarios_disabled = True
    coord._scenarios_last_poll_at = None
    coord._refresh_scenarios = AsyncMock()

    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    coord._refresh_scenarios.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_skips_within_interval():
    """Polling throttling: внутри SCENARIO_POLL_INTERVAL_SEC второй вызов skip."""
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._scenarios_disabled = False
    coord._scenarios_last_poll_at = time.time() - 10  # только что
    coord._refresh_scenarios = AsyncMock()

    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    coord._refresh_scenarios.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_runs_after_interval():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._scenarios_disabled = False
    coord._scenarios_last_poll_at = time.time() - SCENARIO_POLL_INTERVAL_SEC - 1
    coord._refresh_scenarios = AsyncMock()

    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    coord._refresh_scenarios.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_poll_handles_exception_and_sets_disabled():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._scenarios_disabled = False
    coord._scenarios_last_poll_at = None
    coord._refresh_scenarios = AsyncMock(side_effect=RuntimeError("boom"))

    # Не должно бросать наружу — best-effort.
    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    assert coord._scenarios_disabled is True
