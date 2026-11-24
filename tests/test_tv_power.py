"""Issue #95: an uninitialised Salute TV power report must not hide turn_off."""

import httpx
import pytest
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from custom_components.sberhome.const import DOMAIN
from tests.fake_cloud import device


def _tv(*, power=False, timestamp="1970-01-01T00:00:00Z", desired_timestamp=None):
    """Minimal sanitised shape from #95; no real IDs or account metadata."""
    reported = [{"key": "online", "type": "BOOL", "bool_value": True}]
    if power is not None:
        reported.append(
            {"key": "on_off", "type": "BOOL", "bool_value": power, "last_sync": timestamp}
        )
    return device(
        "salute-tv",
        image_set_type="dt_salute_tv_l",
        reported=reported,
        attributes=[{"key": "on_off", "type": "BOOL"}],
        commands=[{"key": "on_off", "state_fields": ["on_off"]}],
        full_categories=[{"slug": "tv"}],
        desired_state=[
            {"key": "on_off", "type": "BOOL", "bool_value": True, "last_sync": desired_timestamp}
        ],
    )


@pytest.mark.parametrize(
    "power,timestamp,desired_timestamp,state,assumed",
    [
        (False, "1970-01-01T00:00:00Z", None, "unknown", True),
        (True, "1970-01-01T00:00:00Z", None, "unknown", True),
        (False, "0001-01-01T00:00:00Z", None, "unknown", True),
        (None, None, None, "unknown", True),
        ("false", "2026-11-24T20:38:59Z", None, "unknown", True),
        (False, "2026-11-24T20:38:59Z", None, "off", False),
        (True, "2026-11-24T20:38:59Z", None, "on", False),
        (False, None, None, "off", False),
        (True, None, None, "on", False),
        (False, "1970-01-01T00:00:00Z", "1970-01-01T00:00:00Z", "unknown", True),
        (False, "1970-01-01T00:00:00Z", "2026-11-24T21:00:00Z", "on", True),
        (False, "2026-11-24T20:38:59Z", "2026-11-24T21:00:00Z", "on", True),
        (False, "2026-11-24T20:38:59Z", "2026-11-24T20:00:00Z", "off", False),
        (True, "2026-11-24T20:38:59Z", "2026-11-24T20:38:59Z", "on", False),
        (True, "2026-11-24T20:38:59Z", "2026-11-24T21:00:00Z", "on", False),
    ],
)
async def test_tv_power_confirmation_controls_state_and_assumption(
    hass, setup_sberhome, fake_cloud, power, timestamp, desired_timestamp, state, assumed
):
    fake_cloud.devices.append(
        _tv(power=power, timestamp=timestamp, desired_timestamp=desired_timestamp)
    )
    await setup_sberhome()
    eid = er.async_get(hass).async_get_entity_id("media_player", DOMAIN, "salute-tv")
    actual = hass.states.get(eid)
    assert actual.state == state
    assert actual.attributes.get("assumed_state", False) is assumed
    features = actual.attributes["supported_features"]
    assert features & MediaPlayerEntityFeature.TURN_ON
    assert features & MediaPlayerEntityFeature.TURN_OFF


@pytest.mark.parametrize("reported,desired,state", [(0, False, "off"), (1, True, "on")])
async def test_non_bool_report_cannot_confirm_desired_power(
    hass, setup_sberhome, fake_cloud, reported, desired, state
):
    raw = _tv(
        power=reported,
        timestamp="2026-11-24T20:38:59Z",
        desired_timestamp="2026-11-24T21:00:00Z",
    )
    raw["desired_state"][0]["bool_value"] = desired
    fake_cloud.devices.append(raw)
    await setup_sberhome()
    eid = er.async_get(hass).async_get_entity_id("media_player", DOMAIN, "salute-tv")
    actual = hass.states.get(eid)
    assert actual.state == state
    assert actual.attributes.get("assumed_state") is True


async def test_unconfirmed_tv_accepts_both_explicit_power_commands(
    hass, setup_sberhome, fake_cloud
):
    fake_cloud.devices.append(_tv())
    await setup_sberhome()
    eid = er.async_get(hass).async_get_entity_id("media_player", DOMAIN, "salute-tv")
    assert hass.states.get(eid).attributes.get("assumed_state") is True
    for service, value in [("turn_on", True), ("turn_off", False)]:
        await hass.services.async_call("media_player", service, {"entity_id": eid}, blocking=True)
        request = fake_cloud.sent("PUT", "/devices/salute-tv/state")[-1]
        body = fake_cloud.body(request)
        assert body["device_id"] == "salute-tv"
        assert body["desired_state"] == [{"key": "on_off", "type": "BOOL", "bool_value": value}]
        assert hass.states.get(eid).state == "unknown"
    assert len(fake_cloud.sent("PUT", "/devices/salute-tv/state")) == 2


async def test_confirmed_tv_report_restores_normal_controls(hass, setup_sberhome, fake_cloud):
    raw = _tv()
    fake_cloud.devices.append(raw)
    entry = await setup_sberhome()
    eid = er.async_get(hass).async_get_entity_id("media_player", DOMAIN, "salute-tv")
    assert hass.states.get(eid).state == "unknown"
    for power, expected in [(True, "on"), (False, "off")]:
        raw["reported_state"][1].update(bool_value=power, last_sync="2026-11-24T22:00:00Z")
        await entry.runtime_data.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(eid).state == expected
        assert not hass.states.get(eid).attributes.get("assumed_state", False)
    raw["reported_state"][0]["bool_value"] = False
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(eid).state == "unavailable"


async def test_tv_power_cloud_error_is_visible(hass, setup_sberhome, fake_cloud):
    fake_cloud.devices.append(_tv())
    await setup_sberhome()
    eid = er.async_get(hass).async_get_entity_id("media_player", DOMAIN, "salute-tv")
    fake_cloud.on("PUT", "/devices/salute-tv/state", lambda _: httpx.Response(403, json={}))
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "media_player", "turn_off", {"entity_id": eid}, blocking=True
        )
