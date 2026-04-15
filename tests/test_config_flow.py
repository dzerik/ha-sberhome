"""Tests for the SberHome config flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from custom_components.sberhome.auth_state import pending_auth_flows
from custom_components.sberhome.config_flow import (
    ConfigFlow,
    SberHomeOptionsFlow,
)
from custom_components.sberhome.const import CONF_SCAN_INTERVAL


def _make_flow_with_source(source: str = "user") -> ConfigFlow:
    """Create a ConfigFlow with a mocked source property."""
    flow = ConfigFlow()
    # source is a read-only property on FlowHandler, so we mock it
    type(flow).source = PropertyMock(return_value=source)
    return flow


@pytest.mark.asyncio
async def test_step_user_starts_external_flow():
    """Test that async_step_user registers views and returns external step."""
    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow.hass.http = MagicMock()
    flow.hass.data = {}
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    flow.flow_id = "test-flow-id"

    with patch(
        "custom_components.sberhome.config_flow.SberAPI"
    ) as mock_sber_cls:
        mock_sber_cls.return_value.create_authorization_url.return_value = (
            "https://example.com/auth"
        )

        def mock_external_step(**kwargs):
            return {"type": "external", **kwargs}

        flow.async_external_step = mock_external_step

        result = await flow.async_step_user(user_input=None)

    assert result["type"] == "external"
    assert "auth/sberhome" in result["url"]
    assert "test-flow-id" in result["url"]
    assert flow.hass.http.register_view.call_count == 2
    assert "test-flow-id" in pending_auth_flows

    # Cleanup
    pending_auth_flows.pop("test-flow-id", None)


@pytest.mark.asyncio
async def test_step_user_completes_external():
    """Test that async_step_user with user_input completes external step."""
    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow._client = AsyncMock()

    called_with = {}

    def mock_external_step_done(**kwargs):
        called_with.update(kwargs)
        return {"type": "external_done", **kwargs}

    flow.async_external_step_done = mock_external_step_done

    result = await flow.async_step_user(user_input={})
    assert called_with["next_step_id"] == "finish"


@pytest.mark.asyncio
async def test_step_finish_creates_entry():
    """Test that finish step creates an entry when token is present."""
    mock_client = AsyncMock()
    mock_client.token = {"access_token": "test-token"}

    flow = _make_flow_with_source("user")
    flow.flow_id = "finish-flow"
    flow._client = mock_client

    created_entry = None

    def mock_create_entry(**kwargs):
        nonlocal created_entry
        created_entry = kwargs
        return {"type": "create_entry", **kwargs}

    flow.async_create_entry = mock_create_entry

    result = await flow.async_step_finish(user_input=None)
    assert created_entry is not None
    assert created_entry["title"] == "SberHome"
    assert created_entry["data"]["token"] == {"access_token": "test-token"}


@pytest.mark.asyncio
async def test_step_finish_aborts_without_token():
    """Test that finish step aborts when no token is available."""
    flow = _make_flow_with_source("user")
    flow.flow_id = "abort-flow"
    flow._client = None

    def mock_abort(**kwargs):
        return {"type": "abort", **kwargs}

    flow.async_abort = mock_abort

    result = await flow.async_step_finish(user_input=None)
    assert result["type"] == "abort"
    assert result["reason"] == "invalid_auth"


@pytest.mark.asyncio
async def test_step_finish_cleans_up_pending():
    """Test that finish step removes flow from pending_auth_flows."""
    flow = _make_flow_with_source("user")
    flow.flow_id = "cleanup-flow"
    flow._client = None
    pending_auth_flows["cleanup-flow"] = MagicMock()

    def mock_abort(**kwargs):
        return {"type": "abort", **kwargs}

    flow.async_abort = mock_abort

    await flow.async_step_finish(user_input=None)
    assert "cleanup-flow" not in pending_auth_flows


# --- Reauth Flow Tests ---


@pytest.mark.asyncio
async def test_step_reauth_shows_confirm_form():
    """Test that async_step_reauth shows reauth_confirm form."""
    flow = ConfigFlow()
    flow.hass = MagicMock()

    def mock_show_form(**kwargs):
        return {"type": "form", **kwargs}

    flow.async_show_form = mock_show_form

    result = await flow.async_step_reauth(entry_data={"token": {}})
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


@pytest.mark.asyncio
async def test_step_reauth_confirm_starts_external_auth():
    """Test that reauth_confirm with user_input starts external OAuth flow."""
    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow.hass.http = MagicMock()
    flow.hass.data = {}
    flow.hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
    flow.flow_id = "reauth-flow-id"

    with patch(
        "custom_components.sberhome.config_flow.SberAPI"
    ) as mock_sber_cls:
        mock_sber_cls.return_value.create_authorization_url.return_value = (
            "https://example.com/auth"
        )

        def mock_external_step(**kwargs):
            return {"type": "external", **kwargs}

        flow.async_external_step = mock_external_step

        result = await flow.async_step_reauth_confirm(user_input={})

    assert result["type"] == "external"
    assert result["step_id"] == "reauth_authorize"
    assert "reauth-flow-id" in pending_auth_flows

    # Cleanup
    pending_auth_flows.pop("reauth-flow-id", None)


@pytest.mark.asyncio
async def test_step_reauth_authorize_completes_external():
    """Test that reauth_authorize with user_input completes external step."""
    flow = ConfigFlow()
    flow.hass = MagicMock()
    flow._client = AsyncMock()

    called_with = {}

    def mock_external_step_done(**kwargs):
        called_with.update(kwargs)
        return {"type": "external_done", **kwargs}

    flow.async_external_step_done = mock_external_step_done

    result = await flow.async_step_reauth_authorize(user_input={})
    assert called_with["next_step_id"] == "finish"


@pytest.mark.asyncio
async def test_step_finish_updates_entry_on_reauth():
    """Test that finish step updates existing entry during reauth."""
    from homeassistant.config_entries import SOURCE_REAUTH

    mock_client = AsyncMock()
    mock_client.token = {"access_token": "new-token"}

    mock_entry = MagicMock()
    mock_entry.data = {"token": {"access_token": "old-token"}}

    flow = _make_flow_with_source(SOURCE_REAUTH)
    flow.flow_id = "reauth-finish-flow"
    flow._client = mock_client

    updated_data = {}

    def mock_update_reload_and_abort(entry, **kwargs):
        updated_data.update(kwargs)
        return {"type": "abort", "reason": "reauth_successful"}

    flow.async_update_reload_and_abort = mock_update_reload_and_abort
    flow._get_reauth_entry = MagicMock(return_value=mock_entry)

    result = await flow.async_step_finish(user_input=None)
    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert updated_data["data_updates"]["token"] == {"access_token": "new-token"}


# --- Options Flow Tests ---


@pytest.mark.asyncio
async def test_options_flow_shows_form():
    """Test that options flow shows form with current values."""
    flow = SberHomeOptionsFlow()

    mock_entry = MagicMock()
    mock_entry.options = {CONF_SCAN_INTERVAL: 60}

    # config_entry is a property that checks self.hass, so mock it
    type(flow).config_entry = PropertyMock(return_value=mock_entry)

    showed_form = {}

    def mock_show_form(**kwargs):
        showed_form.update(kwargs)
        return {"type": "form", **kwargs}

    flow.async_show_form = mock_show_form

    def mock_add_suggested(schema, values):
        return schema

    flow.add_suggested_values_to_schema = mock_add_suggested

    result = await flow.async_step_init(user_input=None)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    # Cleanup PropertyMock
    del type(flow).config_entry


@pytest.mark.asyncio
async def test_options_flow_saves_values():
    """Test that options flow saves user input."""
    flow = SberHomeOptionsFlow()

    created_entry = {}

    def mock_create_entry(**kwargs):
        created_entry.update(kwargs)
        return {"type": "create_entry", **kwargs}

    flow.async_create_entry = mock_create_entry

    result = await flow.async_step_init(
        user_input={CONF_SCAN_INTERVAL: 60}
    )
    assert created_entry["data"][CONF_SCAN_INTERVAL] == 60
