"""Automation entities follow authoritative inventory without losing HA identity."""

import httpx
import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.sberhome.aiosber.dto import SocketMessageDto
from custom_components.sberhome.const import (
    CONF_ENABLED_DEVICE_IDS,
    DOMAIN,
    PRUNE_MIN_CONSECUTIVE_MISSES,
)
from tests.fake_cloud import device


def _group(cloud, *, group_id="group-1", name="Группа"):
    cloud.groups.append(
        {"id": group_id, "name": name, "group_type": "GROUP", "parent_id": "home-1"}
    )
    cloud.devices.append(
        device(
            "member-" + group_id,
            group_ids=["room-1", group_id],
            reported=[
                {"key": "online", "type": "BOOL", "bool_value": True},
                {"key": "on_off", "type": "BOOL", "bool_value": False},
            ],
        )
    )


async def test_unchanged_group_survives_registry_maintenance(hass, setup_sberhome, fake_cloud):
    """The real shared service identifier must survive every successful inventory poll."""
    _group(fake_cloud)
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1")
    assert eid
    device_id = registry.async_get(eid).device_id
    for _ in range(PRUNE_MIN_CONSECUTIVE_MISSES + 1):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert "group-1" in entry.runtime_data.state_cache.get_all_groups()
        assert registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1") == eid
        assert dr.async_get(hass).async_get(device_id) is not None
        assert hass.states.get(eid).state == "off"


async def test_new_scenario_gets_active_switch_once(hass, setup_sberhome, fake_cloud):
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    fake_cloud.scenarios = [{"id": "scene", "name": "Новый", "is_active": False, "steps": []}]
    for _ in range(3):
        await entry.runtime_data.async_refresh_scenarios()
        await hass.async_block_till_done()
    eid = registry.async_get_entity_id("switch", DOMAIN, "sberhome_scenario_active_scene")
    assert eid and hass.states.get(eid).state == "off"
    assert (
        len(
            [
                e
                for e in registry.entities.values()
                if e.unique_id == "sberhome_scenario_active_scene"
            ]
        )
        == 1
    )


@pytest.mark.parametrize("language", ["ru", "en", "be", "kk", "uz"])
async def test_scenario_rename_keeps_custom_name_and_ids(
    hass, setup_sberhome, fake_cloud, language
):
    hass.config.language = language
    fake_cloud.scenarios = [{"id": "scene", "name": "Прежнее", "is_active": True, "steps": []}]
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    uids = [
        ("switch", "sberhome_scenario_active_scene"),
        ("button", "sberhome_scenario_scene"),
        ("button", "sberhome_scenario_stop_scene"),
        ("button", "sberhome_scenario_cancel_scene"),
    ]
    ids = [registry.async_get_entity_id(domain, DOMAIN, uid) for domain, uid in uids]
    registry.async_update_entity(ids[0], name="Моё имя")
    await hass.async_block_till_done()
    fake_cloud.scenarios[0]["name"] = "Новое"
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert "Моё имя" in hass.states.get(ids[0]).attributes["friendly_name"]
    for eid in ids[1:]:
        assert "Новое" in hass.states.get(eid).attributes["friendly_name"]
    assert [registry.async_get_entity_id(domain, DOMAIN, uid) for domain, uid in uids] == ids
    assert registry.async_get(ids[0]).original_name == "Новое"


async def test_group_discovery_rename_and_membership_return(hass, setup_sberhome, fake_cloud):
    _group(fake_cloud)
    fake_cloud.devices.clear()  # An initially empty group is not exposed.
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1") is None
    fake_cloud.groups.clear()
    _group(fake_cloud, name="Наполнена")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    eid = registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1")
    assert eid and hass.states.get(eid).state == "off"
    fake_cloud.groups[0]["name"] = "Переименована"
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert "Переименована" in hass.states.get(eid).attributes["friendly_name"]
    fake_cloud.devices[0]["group_ids"] = ["room-1"]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unavailable"
    fake_cloud.devices[0]["group_ids"].append("group-1")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "off"
    assert registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1") == eid


@pytest.mark.parametrize(
    "replacement", [[], [{"id": "group-1", "name": "Комната", "group_type": "ROOM"}]]
)
async def test_missing_or_retyped_group_is_unavailable_with_orphan_member(
    hass, setup_sberhome, fake_cloud, replacement
):
    _group(fake_cloud)
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1")
    fake_cloud.groups = replacement
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unavailable"
    assert registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1") == eid


async def test_home_inventory_rename_add_remove_and_error(hass, setup_sberhome, fake_cloud):
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    first = registry.async_get_entity_id("switch", DOMAIN, "sberhome_at_home_home-1")
    fake_cloud.homes[0]["name"] = "Переименованный дом"
    fake_cloud.homes.append({"id": "home-2", "name": "Второй дом", "group_type": "HOME"})
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    second = registry.async_get_entity_id("switch", DOMAIN, "sberhome_at_home_home-2")
    assert second and hass.states.get(second).state == "on"
    assert "Переименованный дом" in hass.states.get(first).attributes["friendly_name"]
    fake_cloud.on("GET", "/device_groups", lambda _: httpx.Response(500, json={}))
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert hass.states.get(second).state == "on"  # Error does not erase the inventory.
    fake_cloud.on("GET", "/device_groups", {"result": [fake_cloud.homes[1]]})
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert hass.states.get(first).state == "unavailable"
    assert registry.async_get(first) is not None


async def test_deleted_home_unavailable_when_scenario_request_fails(
    hass, setup_sberhome, fake_cloud
):
    entry = await setup_sberhome()
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("switch", DOMAIN, "sberhome_at_home_home-1")
    assert hass.states.get(eid).state == "on"
    fake_cloud.homes.clear()
    fake_cloud.on("GET", "/scenario/v2/scenario", lambda _: httpx.Response(500, json={}))
    coordinator._scenarios_poll.reset()
    coordinator._scenarios_poll.last_poll_at = None
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert coordinator.last_update_success
    assert coordinator.homes == []
    assert hass.states.get(eid).state == "unavailable"
    assert registry.async_get(eid) is not None


@pytest.mark.parametrize("failed_poll", [False, True])
async def test_unselected_member_push_updates_only_group(
    hass, setup_sberhome, fake_cloud, failed_poll
):
    _group(fake_cloud)
    fake_cloud.devices.append(
        device("selected", reported=[{"key": "online", "type": "BOOL", "bool_value": True}])
    )
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_IDS: ["selected"]})
    coordinator = entry.runtime_data
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1")
    assert hass.states.get(eid).state == "off"
    if failed_poll:
        fake_cloud.down = True
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == "unavailable"
        fake_cloud.down = False
    timer = coordinator._unsub_refresh
    selected_data = dict(coordinator.data)
    msg = SocketMessageDto.from_dict(
        {
            "state": {
                "device_id": "member-group-1",
                "reported_state": [{"key": "on_off", "type": "BOOL", "bool_value": True}],
            }
        }
    )
    await coordinator._on_ws_device_state(msg)
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "on"
    assert coordinator._unsub_refresh is timer
    assert coordinator.data == selected_data
    assert "member-group-1" not in coordinator.data


async def test_scenario_return_keeps_disabled_entity_and_custom_identity(
    hass, setup_sberhome, fake_cloud
):
    fake_cloud.scenarios = [{"id": "scene", "name": "Первое", "is_active": True, "steps": []}]
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    active = registry.async_get_entity_id("switch", DOMAIN, "sberhome_scenario_active_scene")
    cancel = registry.async_get_entity_id("button", DOMAIN, "sberhome_scenario_cancel_scene")
    registry.async_update_entity(active, name="Своё имя", icon="mdi:star")
    registry.async_update_entity(cancel, disabled_by=er.RegistryEntryDisabler.USER)
    await hass.async_block_till_done()
    fake_cloud.scenarios = []
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert hass.states.get(active).state == "unavailable"
    fake_cloud.scenarios = [{"id": "scene", "name": "Возврат", "is_active": False, "steps": []}]
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    assert hass.states.get(active).state == "off"
    assert "Своё имя" in hass.states.get(active).attributes["friendly_name"]
    assert registry.async_get(active).original_name == "Возврат"
    assert registry.async_get(active).icon == "mdi:star"
    assert registry.async_get(cancel).disabled_by is er.RegistryEntryDisabler.USER
    assert (
        registry.async_get_entity_id("button", DOMAIN, "sberhome_scenario_cancel_scene") == cancel
    )


async def test_group_custom_name_survives_disappearance_and_return(
    hass, setup_sberhome, fake_cloud
):
    _group(fake_cloud)
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1")
    registry.async_update_entity(eid, name="Моя группа")
    await hass.async_block_till_done()
    original = fake_cloud.groups.pop()
    for _ in range(PRUNE_MIN_CONSECUTIVE_MISSES + 1):
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unavailable"
    original["name"] = "Вернулась"
    fake_cloud.groups.append(original)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get_entity_id("switch", DOMAIN, "sber_group_group-1") == eid
    assert hass.states.get(eid).state == "off"
    assert "Моя группа" in hass.states.get(eid).attributes["friendly_name"]
    assert registry.async_get(eid).original_name == "Вернулась"


async def test_discovery_stops_on_unload_and_resumes_after_reload(hass, setup_sberhome, fake_cloud):
    fake_cloud.scenarios = [{"id": "first", "name": "Первое", "is_active": True, "steps": []}]
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    before = registry.async_get_entity_id("switch", DOMAIN, "sberhome_scenario_active_first")
    old = entry.runtime_data
    assert await hass.config_entries.async_unload(entry.entry_id)
    from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto

    old.scenarios = [ScenarioDto(id="after-unload", name="После выгрузки")]
    old.async_update_listeners()
    await hass.async_block_till_done()
    assert (
        registry.async_get_entity_id("switch", DOMAIN, "sberhome_scenario_active_after-unload")
        is None
    )
    assert registry.async_get_entity_id("button", DOMAIN, "sberhome_scenario_after-unload") is None
    fake_cloud.scenarios.append({"id": "second", "name": "Второе", "is_active": False, "steps": []})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert (
        registry.async_get_entity_id("switch", DOMAIN, "sberhome_scenario_active_first") == before
    )
    second = registry.async_get_entity_id("switch", DOMAIN, "sberhome_scenario_active_second")
    assert second and hass.states.get(second).state == "off"


@pytest.mark.parametrize(
    "language,word",
    [("ru", "Дома"), ("en", "At home"), ("be", "Дома"), ("kk", "Үйде"), ("uz", "Uyda")],
)
async def test_home_translated_name_follows_rename(
    hass, setup_sberhome, fake_cloud, language, word
):
    hass.config.language = language
    entry = await setup_sberhome()
    registry = er.async_get(hass)
    eid = registry.async_get_entity_id("switch", DOMAIN, "sberhome_at_home_home-1")
    assert word in hass.states.get(eid).attributes["friendly_name"]
    fake_cloud.homes[0]["name"] = "Новое имя"
    await entry.runtime_data.async_refresh_scenarios()
    await hass.async_block_till_done()
    name = hass.states.get(eid).attributes["friendly_name"]
    assert word in name and "Новое имя" in name
