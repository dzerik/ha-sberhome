"""Config flow for SberHome integration."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

# ``OptionsFlowWithReload`` landed in HA 2025.12.  Older HA versions (still
# shipped with some ``pytest-homeassistant-custom-component`` resolutions)
# expose only the plain ``OptionsFlow`` — fall back to it so test collection
# succeeds everywhere.  On the fallback path options changes won't
# auto-reload the entry; the ``async_update_listener`` registered in
# ``__init__.py`` already covers that case.
try:
    from homeassistant.config_entries import OptionsFlowWithReload
except ImportError:  # pragma: no cover — exercised only on old HA builds
    from homeassistant.config_entries import (
        OptionsFlow as OptionsFlowWithReload,  # type: ignore[assignment]
    )

from .aiosber.auth import decode_jwt_unverified
from .aiosber.exceptions import PkceError
from .api import REQUEST_TIMEOUT, SberAPI, async_init_ssl
from .auth_state import PendingFlow, cleanup_expired, pending_auth_flows
from .auth_view import SberAuthCallbackView, SberAuthStartView
from .const import (
    CONF_ENABLED_DEVICE_IDS,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
)

_VIEWS_REGISTERED_KEY = f"{DOMAIN}_views_registered"


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SberHome."""

    VERSION = 2

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
        # Lazy GC: перед регистрацией нового flow очищаем просроченные
        # (abandoned OAuth flows, где пользователь закрыл вкладку).
        # Без этого каждый brought-up-but-not-finished flow оставлял
        # живой httpx.AsyncClient до рестарта HA (P1 #11).
        await cleanup_expired()

        ssl_ctx = await async_init_ssl(self.hass)
        http = httpx.AsyncClient(verify=ssl_ctx, timeout=REQUEST_TIMEOUT)
        self._client = SberAPI(http=http, owns_http=True)
        self._register_views()
        auth_url = self._client.create_authorization_url()
        pending_auth_flows[self.flow_id] = PendingFlow(client=self._client)
        return self.async_external_step(
            step_id=step_id,
            url=f"/auth/sberhome?flow_id={self.flow_id}&auth_url={quote(auth_url, safe='')}",
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        if user_input is None:
            return await self._start_external_auth("user")

        # Called by SberAuthCallbackView after successful auth
        return self.async_external_step_done(next_step_id="finish")

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Create config entry after successful auth."""
        # Clean up pending flow
        pending_auth_flows.pop(self.flow_id, None)

        if self._client and self._client.token:
            token = self._client.token
            # OAuth flow завершён — закрываем httpx (он был создан в
            # `_start_external_auth`). Новый httpx создаётся в
            # `async_setup_entry` как shared для coordinator.
            await self._client.aclose()
            self._client = None

            # Unique ID из JWT id_token `sub` claim — уникален per Sber
            # ID аккаунт. Без этого можно создать 2 записи для одного
            # аккаунта, а reauth не защищён от `wrong_account` случая.
            sub = self._extract_sub(token)
            if sub is not None:
                await self.async_set_unique_id(sub)
                if self.source == config_entries.SOURCE_REAUTH:
                    self._abort_if_unique_id_mismatch(reason="wrong_account")
                else:
                    self._abort_if_unique_id_configured()

            # Reauth: update existing entry
            if self.source == config_entries.SOURCE_REAUTH:
                LOGGER.info("Reauthentication successful, updating config entry")
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_TOKEN: token},
                )
            LOGGER.info("Authorization successful, creating config entry")
            # Opt-in: новый entry стартует с пустым списком включённых устройств,
            # пользователь выбирает их через панель SberHome. Без этого
            # интеграция бы импортировала ВСЕ устройства аккаунта в HA сразу
            # после авторизации, что обычно нежелательно.
            return self.async_create_entry(
                title="SberHome",
                data={CONF_TOKEN: token},
                options={CONF_ENABLED_DEVICE_IDS: []},
            )
        if self._client:
            await self._client.aclose()
            self._client = None
        LOGGER.warning("Authorization failed: no token received")
        return self.async_abort(reason="invalid_auth")

    @staticmethod
    def _extract_sub(token: dict[str, Any]) -> str | None:
        """Декодировать id_token и вернуть `sub` claim.

        Возвращает None если id_token отсутствует или невалиден —
        в этом случае unique_id просто не устанавливается (graceful
        degradation: интеграция работает, но без защиты от дублей).
        """
        id_tok = token.get("id_token")
        if not id_tok:
            return None
        try:
            claims = decode_jwt_unverified(id_tok)
        except PkceError:
            LOGGER.debug("Cannot decode id_token — unique_id skipped", exc_info=True)
            return None
        sub = claims.get("sub")
        return str(sub) if sub else None

    # --- Reauth Flow ---

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
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

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
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
