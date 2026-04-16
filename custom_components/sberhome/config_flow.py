"""Config flow for SberHome integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import SberAPI, async_init_ssl
from .auth_state import pending_auth_flows
from .auth_view import SberAuthCallbackView, SberAuthStartView
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER

_VIEWS_REGISTERED_KEY = f"{DOMAIN}_views_registered"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SberHome."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._client: SberAPI | None = None
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SberHomeOptionsFlow:
        """Create the options flow."""
        return SberHomeOptionsFlow()

    def _register_views(self) -> None:
        """Register auth helper views (once per HA instance)."""
        if not self.hass.data.get(_VIEWS_REGISTERED_KEY):
            self.hass.http.register_view(SberAuthStartView())
            self.hass.http.register_view(SberAuthCallbackView())
            self.hass.data[_VIEWS_REGISTERED_KEY] = True

    async def _start_external_auth(self, step_id: str) -> FlowResult:
        """Start the external OAuth flow."""
        await async_init_ssl(self.hass)
        self._client = SberAPI()
        self._register_views()
        auth_url = self._client.create_authorization_url()
        pending_auth_flows[self.flow_id] = self._client
        return self.async_external_step(
            step_id=step_id,
            url=f"/auth/sberhome?flow_id={self.flow_id}"
            f"&auth_url={quote(auth_url, safe='')}",
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return await self._start_external_auth("user")

        # Called by SberAuthCallbackView after successful auth
        return self.async_external_step_done(next_step_id="finish")

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create config entry after successful auth."""
        # Clean up pending flow
        pending_auth_flows.pop(self.flow_id, None)

        if self._client and self._client.token:
            # Reauth: update existing entry
            if self.source == config_entries.SOURCE_REAUTH:
                LOGGER.info("Reauthentication successful, updating config entry")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={"token": self._client.token},
                )
            LOGGER.info("Authorization successful, creating config entry")
            # Opt-in: новый entry стартует с пустым списком включённых устройств,
            # пользователь выбирает их через панель SberHome. Без этого
            # интеграция бы импортировала ВСЕ устройства аккаунта в HA сразу
            # после авторизации, что обычно нежелательно.
            return self.async_create_entry(
                title="SberHome",
                data={"token": self._client.token},
                options={"enabled_device_ids": []},
            )
        LOGGER.warning("Authorization failed: no token received")
        return self.async_abort(reason="invalid_auth")

    # --- Reauth Flow ---

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauthentication."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauthentication."""
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
            )
        return await self._start_external_auth("reauth_authorize")

    async def async_step_reauth_authorize(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the external auth step during reauth."""
        if user_input is None:
            # This shouldn't happen — external step was already started
            return self.async_abort(reason="invalid_auth")

        # Called by SberAuthCallbackView after successful auth
        return self.async_external_step_done(next_step_id="finish")


class SberHomeOptionsFlow(OptionsFlowWithReload):
    """Handle options for SberHome."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_SCAN_INTERVAL,
                            default=DEFAULT_SCAN_INTERVAL,
                        ): vol.All(int, vol.Range(min=10, max=300)),
                    }
                ),
                self.config_entry.options,
            ),
        )
