"""Home-variable signal handling and distinct per-scenario execution controls."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er

from custom_components.sberhome.aiosber import SocketMessageDto
from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.aiosber.exceptions import ApiError
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.coordinator import SberHomeCoordinator


@pytest.mark.parametrize("operation", ["stop", "cancel"])
async def test_control_button_calls_only_its_operation(operation):
    from custom_components.sberhome.button import SberScenarioControlButton

    coord = MagicMock()
    coord.scenarios = [ScenarioDto(id="one", name="Test")]
    coord.async_stop_scenario = AsyncMock()
    coord.async_cancel_scenario = AsyncMock()
    coord.async_execute_scenario = AsyncMock()
    button = SberScenarioControlButton(coord, "one", "Test", operation)
    await button.async_press()
    getattr(coord, f"async_{operation}_scenario").assert_awaited_once_with("one")
    coord.async_execute_scenario.assert_not_awaited()
    assert button.unique_id == f"sberhome_scenario_{operation}_one"
    assert button.translation_key == f"scenario_{operation}"
    assert button.translation_placeholders == {"name": "Test"}
    coord.scenarios = []
    assert button.available is False


@pytest.mark.parametrize("operation", ["stop", "cancel"])
async def test_coordinator_control_calls_api(operation):
    coord = MagicMock()
    coord._scenario_api.return_value = api = MagicMock()
    setattr(api, operation, AsyncMock())
    await getattr(SberHomeCoordinator, f"async_{operation}_scenario")(coord, "one")
    getattr(api, operation).assert_awaited_once_with("one")


async def test_home_variable_bursts_refresh_again_without_parallel_reads(hass):
    coord = MagicMock(spec=SberHomeCoordinator)
    coord.hass = hass
    coord._home_variable_refresh_task = None
    coord._home_variable_refresh_pending = False
    coord._async_home_variable_refresh = SberHomeCoordinator._async_home_variable_refresh.__get__(
        coord
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def refresh():
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()

    coord.async_refresh_scenarios = AsyncMock(side_effect=refresh)
    msg = SocketMessageDto.from_dict(
        {
            "scenario_home_change_variable": {
                "changeType": "SET_VARIABLE",
                "id": "opaque",
                "variable": {},
            }
        }
    )
    await SberHomeCoordinator._on_ws_home_variable(coord, msg)
    await entered.wait()
    task = coord._home_variable_refresh_task
    for _ in range(4):
        await SberHomeCoordinator._on_ws_home_variable(coord, msg)
    assert coord.async_refresh_scenarios.await_count == 1
    assert coord._home_variable_refresh_task is task
    release.set()
    await task
    assert coord.async_refresh_scenarios.await_count == 2
    assert coord._home_variable_refresh_task is None


@pytest.mark.parametrize("language", ["en", "ru", "be", "kk", "uz"])
async def test_real_entities_discover_once_and_call_cloud(
    hass, setup_sberhome, fake_cloud, language
):
    hass.config.language = language
    fake_cloud.scenarios = [{"id": "one", "name": "First", "is_active": True, "steps": []}]
    for op in ("stop", "cancel"):
        fake_cloud.on("POST", f"/scenario/v2/scenario/one/{op}", {})
    entry = await setup_sberhome()
    registry = er.async_get(hass)

    def entity(unique):
        return registry.async_get_entity_id("button", DOMAIN, unique)

    run = entity("sberhome_scenario_one")
    assert run
    for op in ("stop", "cancel"):
        eid = entity(f"sberhome_scenario_{op}_one")
        assert eid
        names = {
            "en": {"stop": "Stop First", "cancel": "Cancel First"},
            "ru": {"stop": "Остановить First", "cancel": "Отменить First"},
            "be": {"stop": "Спыніць First", "cancel": "Адмяніць First"},
            "kk": {"stop": "First тоқтату", "cancel": "First болдырмау"},
            "uz": {"stop": "First to‘xtatish", "cancel": "First bekor qilish"},
        }
        assert names[language][op] in hass.states.get(eid).attributes["friendly_name"]
        await hass.services.async_call("button", "press", {"entity_id": eid}, blocking=True)
        assert len(fake_cloud.sent("POST", f"/scenario/v2/scenario/one/{op}")) == 1
    assert not fake_cloud.sent("POST", "/scenario/v2/scenario/one/run")
    fake_cloud.scenarios.append({"id": "two", "name": "Second", "is_active": False, "steps": []})
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert entity("sberhome_scenario_stop_two") and entity("sberhome_scenario_cancel_two")
    before = {e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert {
        e.entity_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)
    } == before
    fake_cloud.scenarios = []
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert hass.states.get(entity("sberhome_scenario_stop_two")).state == "unavailable"
    assert entity("sberhome_scenario_one") == run


async def test_real_home_signal_reads_each_home_without_trusting_payload(
    hass, setup_sberhome, fake_cloud
):
    fake_cloud.homes.append({**fake_cloud.homes[0], "id": "home-2", "name": "Second"})
    values = {fake_cloud.homes[0]["id"]: True, "home-2": False}

    def home(request):
        return httpx.Response(
            200,
            json={
                "variable": {
                    "name": "at_home",
                    "value": {"bool_value": values[request.url.params["home_id"]]},
                }
            },
        )

    fake_cloud.on("GET", "/scenario/v2/home/variable/at_home", home)
    entry = await setup_sberhome()
    coord = entry.runtime_data
    assert coord.at_home == values
    values.update({fake_cloud.homes[0]["id"]: False, "home-2": True})
    msg = SocketMessageDto.from_dict(
        {
            "scenario_home_change_variable": {
                "id": "opaque-not-home",
                "variable": {"value": {"bool_value": True}},
            }
        }
    )
    await coord._on_ws_home_variable(msg)
    await coord._home_variable_refresh_task
    await hass.async_block_till_done()
    assert coord.at_home == values
    registry = er.async_get(hass)
    for home_id, value in values.items():
        eid = registry.async_get_entity_id("switch", DOMAIN, "sberhome_at_home_" + home_id)
        assert hass.states.get(eid).state == ("on" if value else "off")
    assert not fake_cloud.sent("PUT", "/scenario/v2/home/variable/at_home")


async def test_worker_recovers_after_error(hass):
    coord = MagicMock(spec=SberHomeCoordinator)
    coord.hass = hass
    coord._home_variable_refresh_task = None
    coord._async_home_variable_refresh = SberHomeCoordinator._async_home_variable_refresh.__get__(
        coord
    )
    coord.async_refresh_scenarios = AsyncMock(side_effect=[RuntimeError("offline"), None])
    msg = SocketMessageDto.from_dict({"scenario_home_change_variable": {"id": "opaque"}})
    for _ in range(2):
        await SberHomeCoordinator._on_ws_home_variable(coord, msg)
        await coord._home_variable_refresh_task
    assert coord.async_refresh_scenarios.await_count == 2
    assert coord._home_variable_refresh_task is None
    await SberHomeCoordinator._on_ws_home_variable(coord, SocketMessageDto())
    assert coord._home_variable_refresh_task is None


async def test_shutdown_cancels_home_worker_and_ignores_late_push(hass, setup_sberhome):
    entry = await setup_sberhome()
    coord = entry.runtime_data
    started = asyncio.Event()
    blocked = asyncio.Event()

    async def refresh():
        started.set()
        await blocked.wait()

    coord.async_refresh_scenarios = AsyncMock(side_effect=refresh)
    msg = SocketMessageDto.from_dict({"scenario_home_change_variable": {"id": "opaque"}})
    await coord._on_ws_home_variable(msg)
    await started.wait()
    task = coord._home_variable_refresh_task
    await coord.async_shutdown()
    assert task.cancelled()
    await coord._on_ws_home_variable(msg)
    assert coord._home_variable_refresh_task is None


@pytest.mark.parametrize("operation", ["stop", "cancel"])
async def test_control_error_uses_ha_translation(operation):
    from custom_components.sberhome.button import SberScenarioControlButton

    coord = MagicMock()
    coord.scenarios = [ScenarioDto(id="one", name="Test")]
    setattr(coord, f"async_{operation}_scenario", AsyncMock(side_effect=ApiError(400, "invalid")))
    with pytest.raises(ServiceValidationError) as error:
        await SberScenarioControlButton(coord, "one", "Test", operation).async_press()
    assert error.value.translation_key == "command_rejected"


async def test_cancel_running_conflict_has_actionable_translation():
    from custom_components.sberhome.button import SberScenarioControlButton

    coord = MagicMock()
    coord.scenarios = [ScenarioDto(id="one", name="Test")]
    coord.async_cancel_scenario = AsyncMock(side_effect=ApiError(409, "not allowed"))
    with pytest.raises(ServiceValidationError) as error:
        await SberScenarioControlButton(coord, "one", "Test", "cancel").async_press()
    assert error.value.translation_key == "scenario_cancel_not_allowed"
