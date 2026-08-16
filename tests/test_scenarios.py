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
    from custom_components.sberhome.coordinator import ThrottledPoll

    coord._scenarios_poll = ThrottledPoll(300, "Scenario")
    coord._ota_poll = ThrottledPoll(3600, "OTA")
    coord._discover_poll = ThrottledPoll(3600, "Discovery")
    coord._indicator_poll = ThrottledPoll(3600, "Indicator")
    # Generic poll + per-domain refresh — реальные реализации (unbound-вызовы
    # _maybe_poll_* делегируют в них; mock-заглушки сломали бы flow).
    coord._throttled_poll = lambda poll, action: SberHomeCoordinator._throttled_poll(
        coord, poll, action
    )
    coord._refresh_ota = lambda: SberHomeCoordinator._refresh_ota(coord)
    coord._refresh_discovery = lambda: SberHomeCoordinator._refresh_discovery(coord)
    coord._refresh_indicator = lambda: SberHomeCoordinator._refresh_indicator(coord)
    api = MagicMock()
    api.execute_command = AsyncMock()
    coord._scenario_api = MagicMock(return_value=api)

    await SberHomeCoordinator.async_execute_scenario(coord, "sc-42")
    api.execute_command.assert_awaited_once_with({"scenario_id": "sc-42"})


@pytest.mark.asyncio
async def test_coordinator_sets_at_home_optimistically():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    from custom_components.sberhome.coordinator import ThrottledPoll

    coord._scenarios_poll = ThrottledPoll(300, "Scenario")
    coord._ota_poll = ThrottledPoll(3600, "OTA")
    coord._discover_poll = ThrottledPoll(3600, "Discovery")
    coord._indicator_poll = ThrottledPoll(3600, "Indicator")
    # Generic poll + per-domain refresh — реальные реализации (unbound-вызовы
    # _maybe_poll_* делегируют в них; mock-заглушки сломали бы flow).
    coord._throttled_poll = lambda poll, action: SberHomeCoordinator._throttled_poll(
        coord, poll, action
    )
    coord._refresh_ota = lambda: SberHomeCoordinator._refresh_ota(coord)
    coord._refresh_discovery = lambda: SberHomeCoordinator._refresh_discovery(coord)
    coord._refresh_indicator = lambda: SberHomeCoordinator._refresh_indicator(coord)
    coord.data = {}
    coord.async_set_updated_data = MagicMock()
    coord._ensure_home_id = AsyncMock()
    coord.home_id = "home-1"
    api = MagicMock()
    api.set_at_home = AsyncMock()
    coord._scenario_api = MagicMock(return_value=api)

    await SberHomeCoordinator.async_set_at_home(coord, True)
    # home_id прокидывается в запись (endpoint требует ?home_id=).
    api.set_at_home.assert_awaited_once_with(True, "home-1")
    # Optimistic patch перед следующим poll'ом.
    assert coord.at_home is True
    coord.async_set_updated_data.assert_called_once()


async def test_ensure_home_id_discovers_first_home():
    """home_id берётся из первого дома `groups.list(group_type='HOME')`."""
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord.home_id = None
    home = MagicMock()
    home.id = "home-xyz"
    groups = MagicMock()
    groups.list = AsyncMock(return_value=[home])
    client = MagicMock()
    client.groups = groups
    coord.client = client

    await SberHomeCoordinator._ensure_home_id(coord)
    assert coord.home_id == "home-xyz"
    groups.list.assert_awaited_once_with(group_type="HOME")


async def test_refresh_scenarios_uses_home_id_for_at_home():
    """at_home опрашивается с обнаруженным home_id."""
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord.home_id = "home-1"
    coord._ensure_home_id = AsyncMock()
    api = MagicMock()
    api.list = AsyncMock(return_value=[])
    api.get_at_home = AsyncMock(return_value=True)
    coord._scenario_api = MagicMock(return_value=api)

    await SberHomeCoordinator._refresh_scenarios(coord)
    api.get_at_home.assert_awaited_once_with("home-1")
    assert coord.at_home is True


async def test_refresh_scenarios_skips_at_home_without_home_id():
    """Без home_id at_home не опрашивается (иначе 400 'bad home id')."""
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord.home_id = None
    coord._ensure_home_id = AsyncMock()
    api = MagicMock()
    api.list = AsyncMock(return_value=[])
    api.get_at_home = AsyncMock()
    coord._scenario_api = MagicMock(return_value=api)

    await SberHomeCoordinator._refresh_scenarios(coord)
    api.get_at_home.assert_not_awaited()
    assert coord.at_home is None


# ---------------------------------------------------------------------------
# Throttling and disabled flag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_poll_skips_when_disabled():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    from custom_components.sberhome.coordinator import ThrottledPoll

    coord._scenarios_poll = ThrottledPoll(300, "Scenario")
    coord._ota_poll = ThrottledPoll(3600, "OTA")
    coord._discover_poll = ThrottledPoll(3600, "Discovery")
    coord._indicator_poll = ThrottledPoll(3600, "Indicator")
    # Generic poll + per-domain refresh — реальные реализации (unbound-вызовы
    # _maybe_poll_* делегируют в них; mock-заглушки сломали бы flow).
    coord._throttled_poll = lambda poll, action: SberHomeCoordinator._throttled_poll(
        coord, poll, action
    )
    coord._refresh_ota = lambda: SberHomeCoordinator._refresh_ota(coord)
    coord._refresh_discovery = lambda: SberHomeCoordinator._refresh_discovery(coord)
    coord._refresh_indicator = lambda: SberHomeCoordinator._refresh_indicator(coord)
    coord._scenarios_poll.disabled = True
    coord._scenarios_poll.last_poll_at = None
    coord._refresh_scenarios = AsyncMock()

    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    coord._refresh_scenarios.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_skips_within_interval():
    """Polling throttling: внутри SCENARIO_POLL_INTERVAL_SEC второй вызов skip."""
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    from custom_components.sberhome.coordinator import ThrottledPoll

    coord._scenarios_poll = ThrottledPoll(300, "Scenario")
    coord._ota_poll = ThrottledPoll(3600, "OTA")
    coord._discover_poll = ThrottledPoll(3600, "Discovery")
    coord._indicator_poll = ThrottledPoll(3600, "Indicator")
    # Generic poll + per-domain refresh — реальные реализации (unbound-вызовы
    # _maybe_poll_* делегируют в них; mock-заглушки сломали бы flow).
    coord._throttled_poll = lambda poll, action: SberHomeCoordinator._throttled_poll(
        coord, poll, action
    )
    coord._refresh_ota = lambda: SberHomeCoordinator._refresh_ota(coord)
    coord._refresh_discovery = lambda: SberHomeCoordinator._refresh_discovery(coord)
    coord._refresh_indicator = lambda: SberHomeCoordinator._refresh_indicator(coord)
    coord._scenarios_poll.disabled = False
    coord._scenarios_poll.last_poll_at = time.time() - 10  # только что
    coord._refresh_scenarios = AsyncMock()

    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    coord._refresh_scenarios.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_runs_after_interval():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    from custom_components.sberhome.coordinator import ThrottledPoll

    coord._scenarios_poll = ThrottledPoll(300, "Scenario")
    coord._ota_poll = ThrottledPoll(3600, "OTA")
    coord._discover_poll = ThrottledPoll(3600, "Discovery")
    coord._indicator_poll = ThrottledPoll(3600, "Indicator")
    # Generic poll + per-domain refresh — реальные реализации (unbound-вызовы
    # _maybe_poll_* делегируют в них; mock-заглушки сломали бы flow).
    coord._throttled_poll = lambda poll, action: SberHomeCoordinator._throttled_poll(
        coord, poll, action
    )
    coord._refresh_ota = lambda: SberHomeCoordinator._refresh_ota(coord)
    coord._refresh_discovery = lambda: SberHomeCoordinator._refresh_discovery(coord)
    coord._refresh_indicator = lambda: SberHomeCoordinator._refresh_indicator(coord)
    coord._scenarios_poll.disabled = False
    coord._scenarios_poll.last_poll_at = time.time() - SCENARIO_POLL_INTERVAL_SEC - 1
    coord._refresh_scenarios = AsyncMock()

    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    coord._refresh_scenarios.assert_awaited_once()


@pytest.mark.asyncio
async def test_maybe_poll_handles_exception_and_sets_disabled():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    from custom_components.sberhome.coordinator import ThrottledPoll

    coord._scenarios_poll = ThrottledPoll(300, "Scenario")
    coord._ota_poll = ThrottledPoll(3600, "OTA")
    coord._discover_poll = ThrottledPoll(3600, "Discovery")
    coord._indicator_poll = ThrottledPoll(3600, "Indicator")
    # Generic poll + per-domain refresh — реальные реализации (unbound-вызовы
    # _maybe_poll_* делегируют в них; mock-заглушки сломали бы flow).
    coord._throttled_poll = lambda poll, action: SberHomeCoordinator._throttled_poll(
        coord, poll, action
    )
    coord._refresh_ota = lambda: SberHomeCoordinator._refresh_ota(coord)
    coord._refresh_discovery = lambda: SberHomeCoordinator._refresh_discovery(coord)
    coord._refresh_indicator = lambda: SberHomeCoordinator._refresh_indicator(coord)
    coord._scenarios_poll.disabled = False
    coord._scenarios_poll.last_poll_at = None
    coord._refresh_scenarios = AsyncMock(side_effect=RuntimeError("boom"))

    # Не должно бросать наружу — best-effort.
    await SberHomeCoordinator._maybe_poll_scenarios(coord)
    assert coord._scenarios_poll.disabled is True
