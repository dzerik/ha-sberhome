"""Config flow for SberHome integration."""

from __future__ import annotations

import time
import uuid
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

from .aiosber.auth import (
    CsafrontTokens,
    PkceParams,
    decode_jwt_unverified,
    exchange_authcode,
    get_smart_home_token,
    send_otp,
    verify_otp,
)
from .aiosber.const import AUTH_METHOD_CSAFRONT, AUTH_METHOD_SBERID
from .aiosber.exceptions import AuthError, InvalidGrant, NetworkError, PkceError
from .api import REQUEST_TIMEOUT, SberAPI, async_init_ssl
from .auth_state import PendingFlow, cleanup_expired, pending_auth_flows
from .auth_view import SberAuthCallbackView, SberAuthStartView
from .const import (
    CONF_AUTH_METHOD,
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
        # CSAFront beta-flow runtime state
        self._csafront_http: httpx.AsyncClient | None = None
        self._csafront_pkce: PkceParams | None = None
        self._csafront_phone: str | None = None
        self._csafront_ouid: str | None = None

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
        """Handle the initial step — menu выбора метода авторизации."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["sberid", "sms"],
        )

    async def async_step_sberid(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Standard SberID OAuth flow — внешний редирект на id.sber.ru."""
        if user_input is None:
            return await self._start_external_auth("sberid")
        # Called by SberAuthCallbackView after successful auth
        return self.async_external_step_done(next_step_id="finish")

    async def async_step_sms(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Beta path: SMS-OTP через CSAFront. Делегирует на phone-форму."""
        return await self.async_step_sms_phone()

    async def async_step_sms_phone(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Шаг 1 SMS-flow: ввод телефона, отправка OTP."""
        errors: dict[str, str] = {}
        if user_input is not None:
            phone = _normalize_phone(user_input.get("phone", ""))
            if not phone:
                errors["phone"] = "invalid_phone"
            else:
                try:
                    await self._csafront_send_otp(phone)
                except InvalidGrant:
                    errors["base"] = "invalid_phone"
                except (AuthError, NetworkError) as err:
                    LOGGER.warning("CSAFront send_otp failed: %s", err)
                    errors["base"] = "send_otp_failed"
                else:
                    return await self.async_step_sms_otp()

        return self.async_show_form(
            step_id="sms_phone",
            data_schema=vol.Schema({vol.Required("phone"): str}),
            errors=errors,
            description_placeholders={
                "example_phone": "78001234567",
            },
        )

    async def async_step_sms_otp(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Шаг 2 SMS-flow: ввод OTP, обмен на токены."""
        errors: dict[str, str] = {}
        if user_input is not None:
            otp = (user_input.get("otp") or "").strip()
            if not otp:
                errors["otp"] = "invalid_otp"
            else:
                try:
                    tokens = await self._csafront_verify_and_exchange(otp)
                except InvalidGrant:
                    errors["base"] = "invalid_otp"
                except (AuthError, NetworkError) as err:
                    LOGGER.warning("CSAFront verify/exchange failed: %s", err)
                    await self._csafront_cleanup()
                    return self.async_abort(reason="cannot_connect")
                else:
                    return await self._csafront_finalize(tokens)

        return self.async_show_form(
            step_id="sms_otp",
            data_schema=vol.Schema({vol.Required("otp"): str}),
            errors=errors,
            description_placeholders={
                "phone": self._csafront_phone or "",
            },
        )

    # --- CSAFront flow helpers ---

    async def _csafront_send_otp(self, phone: str) -> None:
        """Готовим httpx + PKCE, шлём запрос на SMS."""
        # Закрываем предыдущий http (если пользователь вернулся к phone-форме).
        if self._csafront_http is not None:
            await self._csafront_http.aclose()
        ssl_ctx = await async_init_ssl(self.hass)
        self._csafront_http = httpx.AsyncClient(verify=ssl_ctx, timeout=REQUEST_TIMEOUT)
        self._csafront_pkce = PkceParams.generate()
        self._csafront_phone = phone
        self._csafront_ouid = await send_otp(self._csafront_http, phone, self._csafront_pkce)
        LOGGER.debug("CSAFront SMS sent for phone=%s", phone)

    async def _csafront_verify_and_exchange(self, otp: str) -> CsafrontTokens:
        """Verify OTP → exchange authcode → fetch SmartHomeToken → CsafrontTokens."""
        assert self._csafront_http is not None
        assert self._csafront_pkce is not None
        assert self._csafront_ouid is not None
        assert self._csafront_phone is not None

        authcode = await verify_otp(self._csafront_http, self._csafront_ouid, otp)
        token_data = await exchange_authcode(self._csafront_http, authcode, self._csafront_pkce)
        smart_home_token = await get_smart_home_token(
            self._csafront_http, token_data["access_token"]
        )
        now = time.time()
        return CsafrontTokens(
            csafront_access_token=token_data["access_token"],
            csafront_refresh_token=token_data["refresh_token"],
            smart_home_token=smart_home_token,
            client_uuid=str(uuid.uuid4()),
            csafront_expires_in=int(token_data.get("expires_in", 1800)),
            csafront_obtained_at=now,
            smart_home_obtained_at=now,
            phone=self._csafront_phone,
        )

    async def _csafront_cleanup(self) -> None:
        """Закрыть httpx и обнулить runtime-state."""
        if self._csafront_http is not None:
            await self._csafront_http.aclose()
            self._csafront_http = None
        self._csafront_pkce = None
        self._csafront_ouid = None

    async def _csafront_finalize(self, tokens: CsafrontTokens) -> FlowResult:
        """Создать/обновить config entry с CsafrontTokens."""
        phone = self._csafront_phone or ""
        await self._csafront_cleanup()

        # Unique ID по телефону — один entry на номер.
        await self.async_set_unique_id(f"csafront:{phone}")
        if self.source == config_entries.SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            LOGGER.info("CSAFront reauth successful, updating entry")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates={
                    CONF_AUTH_METHOD: AUTH_METHOD_CSAFRONT,
                    "csafront_tokens": tokens.to_dict(),
                },
            )
        self._abort_if_unique_id_configured()

        LOGGER.info("CSAFront authorization successful, creating entry phone=%s", phone)
        return self.async_create_entry(
            title=f"SberHome (SMS · {phone})",
            data={
                CONF_AUTH_METHOD: AUTH_METHOD_CSAFRONT,
                "csafront_tokens": tokens.to_dict(),
            },
            options={CONF_ENABLED_DEVICE_IDS: []},
        )

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
                    data_updates={
                        CONF_AUTH_METHOD: AUTH_METHOD_SBERID,
                        CONF_TOKEN: token,
                    },
                )
            LOGGER.info("Authorization successful, creating config entry")
            # Opt-in: новый entry стартует с пустым списком включённых устройств,
            # пользователь выбирает их через панель SberHome. Без этого
            # интеграция бы импортировала ВСЕ устройства аккаунта в HA сразу
            # после авторизации, что обычно нежелательно.
            return self.async_create_entry(
                title="SberHome",
                data={
                    CONF_AUTH_METHOD: AUTH_METHOD_SBERID,
                    CONF_TOKEN: token,
                },
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
        """Handle reauthentication — диспатч на тот же flow что использовался изначально."""
        # Csafront entries: предзаполним phone для удобства.
        method = entry_data.get(CONF_AUTH_METHOD)
        if method == AUTH_METHOD_CSAFRONT:
            csaf = entry_data.get("csafront_tokens") or {}
            self._csafront_phone = csaf.get("phone")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm reauthentication."""
        entry = self._get_reauth_entry()
        method = entry.data.get(CONF_AUTH_METHOD)
        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "method": "SMS" if method == AUTH_METHOD_CSAFRONT else "Sber ID",
                },
            )
        if method == AUTH_METHOD_CSAFRONT:
            return await self.async_step_sms_phone()
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


def _normalize_phone(raw: str) -> str | None:
    """Очистить ввод и проверить формат телефона.

    Принимает варианты `+7 800 123 45 67`, `8 800 …`, `78001234567` —
    возвращает `78001234567` (формат CSAFront API: E.164 без `+`).
    None если не похоже на телефон.
    """
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    # 8XXXXXXXXXX → 7XXXXXXXXXX (Russia)
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    # 10 цифр без кода страны — добавим 7
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) < 10 or len(digits) > 15:
        return None
    return digits


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
