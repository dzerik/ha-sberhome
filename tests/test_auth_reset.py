"""Manual credential reset through actual HA options and entry lifecycle."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome._ha_token_store import HACsafrontTokenStore, HATokenStore
from custom_components.sberhome.aiosber.auth import CompanionTokens, CsafrontTokens, SberIdTokens
from custom_components.sberhome.aiosber.const import AUTH_METHOD_CSAFRONT, AUTH_METHOD_SBERID
from custom_components.sberhome.const import CONF_AUTH_METHOD, CONF_ENABLED_DEVICE_IDS, DOMAIN

from .fake_cloud import COMPANION_TOKENS, SBERID_TOKEN, device

AUTH_KEYS = {
    "token",
    "companion_tokens",
    "csafront_tokens",
    "companion_settings_tokens",
    "sberid_tokens",
}


def _credentials(method):
    return {
        CONF_AUTH_METHOD: method,
        "token": dict(SBERID_TOKEN),
        "companion_tokens": dict(COMPANION_TOKENS),
        "csafront_tokens": CsafrontTokens(
            "sms-access", "sms-refresh", "gateway", "old-uuid"
        ).to_dict(),
        "companion_settings_tokens": {
            "access_token": "speaker",
            "refresh_token": "speaker-refresh",
        },
        "sberid_tokens": {"access_token": "legacy"},
        "unrelated": {"keep": True},
    }


async def _reset_form(hass, entry):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert set(result["menu_options"]) == {"settings", "reset_auth"}
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "reset_auth"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reset_auth"
    return result


@pytest.mark.parametrize("method", [AUTH_METHOD_SBERID, AUTH_METHOD_CSAFRONT])
async def test_confirmed_reset_removes_all_credentials_and_preserves_identity(
    hass, sberhome_integration, method
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="same-account",
        data=_credentials(method),
        options={CONF_ENABLED_DEVICE_IDS: ["dev-1"], "command_timeout": 25},
    )
    entry.add_to_hass(hass)
    other = MockConfigEntry(domain=DOMAIN, data={"token": {"access_token": "other"}})
    other.add_to_hass(hass)
    before = deepcopy(dict(entry.data))
    result = await _reset_form(hass, entry)
    assert dict(entry.data) == before

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_started"
    assert AUTH_KEYS.isdisjoint(entry.data)
    assert entry.data[CONF_AUTH_METHOD] == method
    assert entry.data["unrelated"] == {"keep": True}
    assert entry.data["auth_generation"] == 1
    assert entry.unique_id == "same-account"
    assert entry.options == {CONF_ENABLED_DEVICE_IDS: ["dev-1"], "command_timeout": 25}
    assert other.data == {"token": {"access_token": "other"}}
    flows = list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"
    for flow in flows:
        hass.config_entries.flow.async_abort(flow["flow_id"])


async def test_reset_confirmation_cancel_keeps_running_session(hass, setup_sberhome):
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_IDS: ["dev-1"]})
    coordinator = entry.runtime_data
    http = coordinator._shared_http
    before = deepcopy(dict(entry.data))
    result = await _reset_form(hass, entry)
    hass.config_entries.options.async_abort(result["flow_id"])
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is coordinator
    assert not http.is_closed
    assert dict(entry.data) == before
    assert not list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))


async def test_reset_unload_failure_does_not_delete_credentials(hass, setup_sberhome):
    entry = await setup_sberhome()
    hass.config_entries.async_update_entry(entry, unique_id="same-account")
    before = deepcopy(dict(entry.data))
    http = entry.runtime_data._shared_http
    result = await _reset_form(hass, entry)
    with patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)):
        result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_unload"}
    assert dict(entry.data) == before
    assert not http.is_closed
    assert not list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))
    # FAILED_UNLOAD is deliberately unrecoverable until a restart; finish test cleanup.
    entry._async_set_state(hass, ConfigEntryState.LOADED, None)
    hass.config_entries.options.async_abort(result["flow_id"])


@pytest.mark.parametrize("method", [AUTH_METHOD_SBERID, AUTH_METHOD_CSAFRONT])
async def test_reset_stops_clients_and_preserves_registries(
    hass, setup_sberhome, fake_cloud, method
):
    data = _credentials(method)
    fake_cloud.devices = [device("dev-1")]
    # Setup migration normally removes credentials belonging to the other login method.
    entry = await setup_sberhome(data=data, options={CONF_ENABLED_DEVICE_IDS: ["dev-1"]})
    hass.config_entries.async_update_entry(entry, unique_id="same-account")
    assert entry.state is ConfigEntryState.LOADED
    coordinator = entry.runtime_data
    http = coordinator._shared_http
    ws_task = coordinator._ws_task
    entities = dict(er.async_get(hass).entities)
    devices = dict(dr.async_get(hass).devices)
    assert any(item.platform == DOMAIN for item in entities.values())
    assert any(entry.entry_id in item.config_entries for item in devices.values())
    result = await _reset_form(hass, entry)
    await hass.config_entries.options.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert http.is_closed
    assert ws_task is None or ws_task.done()
    assert coordinator._ws_task is None
    assert coordinator._shared_http is None
    assert dict(er.async_get(hass).entities) == entities
    assert dict(dr.async_get(hass).devices) == devices
    assert AUTH_KEYS.isdisjoint(entry.data)
    assert entry.options[CONF_ENABLED_DEVICE_IDS] == ["dev-1"]
    for flow in entry.async_get_active_flows(hass, {SOURCE_REAUTH}):
        hass.config_entries.flow.async_abort(flow["flow_id"])


@pytest.mark.parametrize("method", [AUTH_METHOD_SBERID, AUTH_METHOD_CSAFRONT])
async def test_restart_after_reset_requires_reauth_without_cloud_request(
    hass, setup_sberhome, fake_cloud, method
):
    entry = await setup_sberhome(data={CONF_AUTH_METHOD: method, "auth_generation": 1})
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert fake_cloud.requests == []
    assert AUTH_KEYS.isdisjoint(entry.data)
    flows = list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))
    assert len(flows) == 1
    assert flows[0]["step_id"] == "reauth_confirm"
    hass.config_entries.flow.async_abort(flows[0]["flow_id"])


@pytest.mark.parametrize("restored", [False, True])
async def test_old_token_stores_cannot_read_or_modify_reset_credentials(hass, restored):
    entry = MockConfigEntry(domain=DOMAIN, data=_credentials(AUTH_METHOD_SBERID))
    entry.add_to_hass(hass)
    oauth = HATokenStore(hass, entry)
    settings = HATokenStore(hass, entry, sberid_key="companion_settings_tokens")
    sms = HACsafrontTokenStore(hass, entry)
    new = _credentials(AUTH_METHOD_SBERID) if restored else {CONF_AUTH_METHOD: AUTH_METHOD_SBERID}
    new["auth_generation"] = 1
    hass.config_entries.async_update_entry(entry, data=new)
    before = deepcopy(dict(entry.data))
    assert await oauth.load() is None
    assert await sms.load() is None
    await oauth.save(CompanionTokens(access_token="late-gateway"))
    await oauth.save_sberid(SberIdTokens(access_token="late-oauth"))
    await settings.save_sberid(SberIdTokens(access_token="late-settings"))
    await sms.save_refreshed(CsafrontTokens("late", "late", "late", "late"))
    await oauth.clear()
    await sms.clear()
    assert dict(entry.data) == before
    # New-generation stores remain fully usable after reauthentication.
    current = HATokenStore(hass, entry)
    await current.save(CompanionTokens(access_token="new-gateway"))
    assert (await current.load()).access_token == "new-gateway"
