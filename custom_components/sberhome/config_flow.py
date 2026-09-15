"""Config flow for SberHome integration."""

from __future__ import annotations

import time
import uuid
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.network import NoURLAvailableError, get_url

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

from ._ha_token_store import CONF_COMPANION_TOKENS, CONF_CSAFRONT_TOKENS
from .aiosber.api import GroupAPI
from .aiosber.auth import (
    AuthManager,
    AuthManagerProtocol,
    CompanionTokens,
    CsafrontAuthManager,
    CsafrontTokens,
    InMemoryCsafrontTokenStore,
    InMemoryTokenStore,
    PkceParams,
    SberIdTokens,
    decode_jwt_unverified,
    exchange_authcode,
    get_smart_home_token,
    send_otp,
    verify_otp,
)
from .aiosber.const import AUTH_METHOD_CSAFRONT, AUTH_METHOD_SBERID
from .aiosber.exceptions import AuthError, InvalidGrant, PkceError, SberError
from .aiosber.transport import HttpTransport
from .api import REQUEST_TIMEOUT, SberAPI, async_init_ssl
from .auth_state import PendingFlow, cleanup_expired, pending_auth_flows
from .auth_view import SberAuthCallbackView, SberAuthStartView
from .const import (
    CONF_AUTH_METHOD,
    CONF_COMMAND_TIMEOUT,
    CONF_DEVTOOLS_BUFFER_SIZE,
    CONF_ENABLED_DEVICE_IDS,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_DEVTOOLS_BUFFER_SIZE,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .settings import SETTINGS_LIMITS

_VIEWS_REGISTERED_KEY = f"{DOMAIN}_views_registered"

CONF_PHONE = "phone"
"""Поле формы входа по SMS: номер телефона."""

CONF_OTP = "otp"
"""Поле формы входа по SMS: одноразовый код."""

CONF_RESEND = "resend"
"""Флажок формы входа по SMS: отправить новый код вместо проверки введённого."""

CSAFRONT_UNIQUE_ID_PREFIX = "csafront:"
"""Префикс unique_id записи со входом по SMS (дальше — номер телефона)."""


def _flow_error(err: Exception, action: str) -> str:
    """Перевести исключение при входе в ключ ошибки формы.

    Args:
        err: Исключение, пойманное при обращении к облаку Сбера.
        action: Что делал flow — для журнала.

    Returns:
        ``invalid_auth`` — Сбер отверг данные входа; ``cannot_connect`` — облако
        недоступно или ответило ошибкой; ``unknown`` — непредвиденная ошибка
        (пишется в журнал с трассировкой).
    """
    if isinstance(err, AuthError):
        LOGGER.warning("%s: Sber rejected the credentials: %s", action, err)
        return "invalid_auth"
    if isinstance(err, SberError):
        LOGGER.warning("%s: Sber cloud is unavailable: %s", action, err)
        return "cannot_connect"
    LOGGER.error("%s: unexpected error", action, exc_info=err)
    return "unknown"


async def _async_probe_gateway(http: httpx.AsyncClient, auth: AuthManagerProtocol) -> None:
    """Сделать один лёгкий запрос к шлюзу умного дома Сбера.

    Запрашивается список домов аккаунта (``GET /device_groups?group_type=HOME``)
    — тот же запрос, которым координатор ищет дома. Перед ним ``auth`` получает
    токен умного дома (у Сбер ID — обмен на companion-токен), так что проверка
    проходит весь путь, который потом пройдёт настройка записи.

    Args:
        http: httpx-клиент flow; не закрывается.
        auth: Менеджер токенов проверяемого способа входа.

    Raises:
        AuthError: Сбер отверг данные входа.
        SberError: Облако недоступно или ответило ошибкой.
    """
    await GroupAPI(HttpTransport(http=http, auth=auth)).list(group_type="HOME")


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SberHome.

    Два способа входа — Сбер ID (внешний шаг в браузере) и SMS-код (CSAFront).
    Перед созданием или обновлением записи оба проверяют, что с полученными
    токенами шлюз умного дома действительно отвечает; при ошибке пользователь
    видит её в форме и может повторить. Все httpx-клиенты flow закрываются на
    любом исходе, включая закрытие диалога посреди входа (``async_remove``).
    """

    VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._client: SberAPI | None = None
        # Сбер ID: токены после обмена кода и companion-токены после проверки.
        self._sberid_tokens: SberIdTokens | None = None
        self._companion_tokens: CompanionTokens | None = None
        # CSAFront (вход по SMS)
        self._csafront_http: httpx.AsyncClient | None = None
        self._csafront_pkce: PkceParams | None = None
        self._csafront_phone: str | None = None
        self._csafront_ouid: str | None = None
        self._csafront_tokens: CsafrontTokens | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> SberHomeOptionsFlow:
        """Create the options flow."""
        return SberHomeOptionsFlow()

    @callback
    def async_remove(self) -> None:
        """Закрыть httpx-клиенты, когда Home Assistant убирает flow.

        Вызывается и после завершения flow (запись создана, flow прерван), и
        когда пользователь закрыл диалог посреди входа: на внешнем шаге Сбер ID
        или на форме SMS-кода. Без этого клиент жил бы до истечения
        ``pending_auth_flows`` или до перезапуска Home Assistant.
        """
        pending_auth_flows.pop(self.flow_id, None)
        client, http = self._client, self._csafront_http
        self._client = None
        self._csafront_http = None
        if client is None and http is None:
            return
        self.hass.async_create_task(
            _async_close_clients(client, http), f"{DOMAIN} config flow cleanup"
        )

    def _register_views(self) -> None:
        """Register auth helper views (once per HA instance)."""
        if not self.hass.data.get(_VIEWS_REGISTERED_KEY):
            self.hass.http.register_view(SberAuthStartView())
            self.hass.http.register_view(SberAuthCallbackView())
            self.hass.data[_VIEWS_REGISTERED_KEY] = True

    async def _async_create_http(self) -> httpx.AsyncClient:
        """Создать httpx-клиент с общим SSL-контекстом интеграции."""
        ssl_ctx = await async_init_ssl(self.hass)
        return httpx.AsyncClient(verify=ssl_ctx, timeout=REQUEST_TIMEOUT)

    def _abort_if_other_account(self) -> None:
        """Прервать flow, если вход выполнен не в тот аккаунт.

        Reauth: аккаунт должен совпасть с записью (``wrong_account``). Запись без
        unique_id сверить не с чем — она получит unique_id при обновлении.
        Новая настройка: аккаунт ещё не добавлен (``already_configured``).

        Raises:
            AbortFlow: Аккаунт не тот или уже настроен.
        """
        if self.source == config_entries.SOURCE_REAUTH:
            if self._get_reauth_entry().unique_id is not None:
                self._abort_if_unique_id_mismatch(reason="wrong_account")
        else:
            self._abort_if_unique_id_configured()

    async def _start_external_auth(self, step_id: str) -> FlowResult:
        """Start the external OAuth flow.

        Повторный вызов на том же внешнем шаге (фронтенд перечитывает flow
        запросом без данных) отдаёт ту же ссылку: страница входа уже могла
        получить PKCE-параметры этого клиента, а новый клиент без закрытия
        старого остался бы висеть.
        """
        # Lazy GC: перед регистрацией нового flow очищаем просроченные
        # (abandoned OAuth flows, где пользователь закрыл вкладку).
        # Без этого каждый brought-up-but-not-finished flow оставлял
        # живой httpx.AsyncClient до рестарта HA (P1 #11).
        await cleanup_expired()

        # HA-фронт (2024.x+) прогоняет external_step.url через `new URL(url)`
        # без base — относительный `/auth/sberhome?...` бросает TypeError, и
        # ни попап, ни кнопка «Открыть сайт» не появляются. Отдаём абсолютный.
        # Адрес ищем до создания httpx-клиента: без адреса flow прерывается,
        # и клиент было бы некому закрыть.
        try:
            base = get_url(self.hass, prefer_external=True, allow_internal=True, allow_ip=True)
        except NoURLAvailableError:
            return self.async_abort(reason="no_url_available")

        if self._client is None or self.flow_id not in pending_auth_flows:
            if self._client is not None:
                # Вход не завершён за отведённое время: cleanup_expired уже
                # закрыл этот клиент, начинаем заново.
                await self._client.aclose()
            self._client = SberAPI(http=await self._async_create_http(), owns_http=True)
            self._register_views()
            auth_url = self._client.create_authorization_url()
            pending_auth_flows[self.flow_id] = PendingFlow(client=self._client, auth_url=auth_url)
        # Ссылку на Сбер ID в query не кладём: страница берёт её из
        # pending_auth_flows, иначе её можно подменить в чужой ссылке.
        return self.async_external_step(
            step_id=step_id,
            url=f"{base}/auth/sberhome?flow_id={quote(self.flow_id, safe='')}",
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
        """Шаг 1 SMS-flow: ввод телефона, отправка OTP.

        Аккаунт входа по SMS — номер телефона, поэтому unique_id сверяется ещё
        до отправки SMS: при reauth чужой номер прерывает flow сразу, а не после
        ввода кода.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            phone = _normalize_phone(user_input.get(CONF_PHONE, ""))
            if not phone:
                errors[CONF_PHONE] = "invalid_phone"
            else:
                await self.async_set_unique_id(f"{CSAFRONT_UNIQUE_ID_PREFIX}{phone}")
                self._abort_if_other_account()
                if error := await self._csafront_send_otp(phone):
                    errors["base"] = error
                else:
                    return await self.async_step_sms_otp()

        schema = vol.Schema({vol.Required(CONF_PHONE): str})
        if self._csafront_phone:
            schema = self.add_suggested_values_to_schema(schema, {CONF_PHONE: self._csafront_phone})
        return self.async_show_form(
            step_id="sms_phone",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "example_phone": "78001234567",
            },
        )

    async def async_step_sms_otp(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Шаг 2 SMS-flow: ввод OTP, обмен на токены, проверка облака.

        Флажок ``resend`` отправляет новый код на тот же номер. Если код уже
        принят, а проверка облака не прошла (``cannot_connect``/``unknown``),
        повторная отправка формы повторяет только проверку — код одноразовый.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input.get(CONF_RESEND):
                assert self._csafront_phone is not None
                if error := await self._csafront_send_otp(self._csafront_phone):
                    errors["base"] = error
            else:
                if self._csafront_tokens is None:
                    otp = (user_input.get(CONF_OTP) or "").strip()
                    if not otp:
                        errors[CONF_OTP] = "invalid_otp"
                    elif error := await self._csafront_login(otp):
                        errors["base"] = error
                if not errors:
                    if error := await self._csafront_check_smart_home():
                        errors["base"] = error
                    else:
                        return await self._csafront_finalize()

        return self.async_show_form(
            step_id="sms_otp",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_OTP): str,
                    vol.Optional(CONF_RESEND, default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "phone": self._csafront_phone or "",
            },
        )

    # --- CSAFront flow helpers ---

    async def _csafront_send_otp(self, phone: str) -> str | None:
        """Готовим httpx + PKCE, шлём запрос на SMS.

        Args:
            phone: Нормализованный номер телефона.

        Returns:
            None, если SMS отправлено; иначе ключ ошибки формы
            (``send_otp_failed`` или ``unknown``). При ошибке клиент закрыт.
        """
        # Предыдущий клиент (повторная отправка, возврат к номеру) закрываем.
        await self._csafront_cleanup()
        self._csafront_http = await self._async_create_http()
        self._csafront_pkce = PkceParams.generate()
        self._csafront_phone = phone
        try:
            self._csafront_ouid = await send_otp(self._csafront_http, phone, self._csafront_pkce)
        except Exception as err:
            await self._csafront_cleanup()
            if isinstance(err, SberError):
                LOGGER.warning("CSAFront send_otp failed: %s", err)
                return "send_otp_failed"
            return _flow_error(err, "SMS code request")
        LOGGER.debug("CSAFront SMS sent for phone=***%s", phone[-4:])
        return None

    async def _csafront_login(self, otp: str) -> str | None:
        """Verify OTP → exchange authcode → fetch SmartHomeToken → CsafrontTokens.

        Args:
            otp: Код из SMS.

        Returns:
            None, если токены получены (``self._csafront_tokens``); иначе ключ
            ошибки формы: ``invalid_otp`` (код неверный, просрочен или уже
            использован), ``invalid_auth``, ``cannot_connect`` или ``unknown``.
        """
        if self._csafront_http is None or self._csafront_ouid is None:
            # Код не был отправлен (повторная отправка не удалась) или уже
            # обменян — нужен новый.
            return "invalid_otp"
        assert self._csafront_pkce is not None

        try:
            authcode = await verify_otp(self._csafront_http, self._csafront_ouid, otp)
        except InvalidGrant:
            return "invalid_otp"
        except Exception as err:
            return _flow_error(err, "SMS code check")
        # Код принят и больше не действителен: при сбое дальше нужен новый.
        self._csafront_ouid = None

        try:
            token_data = await exchange_authcode(self._csafront_http, authcode, self._csafront_pkce)
            smart_home_token = await get_smart_home_token(
                self._csafront_http, token_data["access_token"]
            )
        except Exception as err:
            return _flow_error(err, "SMS sign-in")

        now = time.time()
        self._csafront_tokens = CsafrontTokens(
            csafront_access_token=token_data["access_token"],
            csafront_refresh_token=token_data["refresh_token"],
            smart_home_token=smart_home_token,
            client_uuid=str(uuid.uuid4()),
            csafront_expires_in=int(token_data.get("expires_in", 1800)),
            csafront_obtained_at=now,
            smart_home_obtained_at=now,
            phone=self._csafront_phone,
        )
        return None

    async def _csafront_check_smart_home(self) -> str | None:
        """Проверить шлюз умного дома с токенами входа по SMS.

        Returns:
            None при успехе, иначе ключ ошибки формы. При ``invalid_auth``
            токены сбрасываются — нужен новый код. Токены, обновлённые во время
            проверки (одноразовый refresh_token), сохраняются во flow.
        """
        assert self._csafront_http is not None
        assert self._csafront_tokens is not None
        store = InMemoryCsafrontTokenStore()
        auth = CsafrontAuthManager(
            http=self._csafront_http, store=store, initial=self._csafront_tokens
        )
        try:
            await _async_probe_gateway(self._csafront_http, auth)
        except Exception as err:
            error = _flow_error(err, "Sber smart home check")
            self._csafront_tokens = (
                None if error == "invalid_auth" else (await store.load() or self._csafront_tokens)
            )
            return error
        self._csafront_tokens = await store.load() or self._csafront_tokens
        return None

    async def _csafront_cleanup(self) -> None:
        """Закрыть httpx и обнулить runtime-state (номер телефона остаётся)."""
        if self._csafront_http is not None:
            await self._csafront_http.aclose()
            self._csafront_http = None
        self._csafront_pkce = None
        self._csafront_ouid = None
        self._csafront_tokens = None

    async def _csafront_finalize(self) -> FlowResult:
        """Создать/обновить config entry с проверенными CsafrontTokens."""
        assert self._csafront_tokens is not None
        tokens = self._csafront_tokens
        phone = self._csafront_phone or ""
        await self._csafront_cleanup()

        self._abort_if_other_account()
        data = {
            CONF_AUTH_METHOD: AUTH_METHOD_CSAFRONT,
            CONF_CSAFRONT_TOKENS: tokens.to_dict(),
        }
        if self.source == config_entries.SOURCE_REAUTH:
            LOGGER.info("CSAFront reauth successful, updating entry")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), unique_id=self.unique_id, data_updates=data
            )

        LOGGER.info("CSAFront authorization successful, creating entry phone=***%s", phone[-4:])
        return self.async_create_entry(
            title=f"SberHome (SMS · {phone})",
            data=data,
            options={CONF_ENABLED_DEVICE_IDS: []},
        )

    # --- Sber ID flow helpers ---

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Проверить облако и создать/обновить запись после входа через Сбер ID."""
        pending_auth_flows.pop(self.flow_id, None)
        if self._client is not None:
            self._sberid_tokens = self._client.sberid_tokens
            # OAuth-клиент нужен был только для обмена кода на токены (он
            # создан в `_start_external_auth`). Для проверки облака и для
            # записи создаются свои клиенты.
            await self._client.aclose()
            self._client = None
        if self._sberid_tokens is None:
            LOGGER.warning("Authorization failed: no token received")
            return self.async_abort(reason="invalid_auth")

        # Unique ID из JWT id_token `sub` claim — уникален per Sber ID аккаунт.
        # Главное назначение — reauth: без него нельзя отличить вход в чужой
        # аккаунт (`wrong_account`). Вторую запись HA не даёт создать и так
        # (`single_config_entry` в манифесте); проверка на дубль — страховка.
        await self.async_set_unique_id(self._extract_sub(self._sberid_tokens.to_dict()))
        self._abort_if_other_account()

        if error := await self._async_check_sberid():
            return self.async_show_form(
                step_id="sberid_retry",
                data_schema=vol.Schema({}),
                errors={"base": error},
            )

        data: dict[str, Any] = {
            CONF_AUTH_METHOD: AUTH_METHOD_SBERID,
            CONF_TOKEN: self._sberid_tokens.to_dict(),
        }
        if self._companion_tokens is not None:
            data[CONF_COMPANION_TOKENS] = self._companion_tokens.to_dict()

        if self.source == config_entries.SOURCE_REAUTH:
            LOGGER.info("Reauthentication successful, updating config entry")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), unique_id=self.unique_id, data_updates=data
            )
        LOGGER.info("Authorization successful, creating config entry")
        # Opt-in: новый entry стартует с пустым списком включённых устройств,
        # пользователь выбирает их через панель SberHome. Без этого
        # интеграция бы импортировала ВСЕ устройства аккаунта в HA сразу
        # после авторизации, что обычно нежелательно.
        return self.async_create_entry(
            title="SberHome",
            data=data,
            options={CONF_ENABLED_DEVICE_IDS: []},
        )

    async def async_step_sberid_retry(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Повторить после неудачной проверки облака (вход через Сбер ID).

        Если Сбер отверг токены, открывается новый вход через Сбер ID; если
        облако было недоступно, проверка повторяется с уже полученными токенами.
        """
        if self._sberid_tokens is None:
            step_id = (
                "reauth_authorize" if self.source == config_entries.SOURCE_REAUTH else "sberid"
            )
            return await self._start_external_auth(step_id)
        return await self.async_step_finish()

    async def _async_check_sberid(self) -> str | None:
        """Проверить шлюз умного дома с токенами Сбер ID.

        Обменивает Сбер ID на companion-токен и делает запрос к шлюзу через
        короткоживущий httpx-клиент, закрываемый на любом исходе.

        Returns:
            None при успехе (companion-токены — в ``self._companion_tokens``),
            иначе ключ ошибки формы. При ``invalid_auth`` токены Сбер ID
            сбрасываются — нужен новый вход.
        """
        assert self._sberid_tokens is not None
        store = InMemoryTokenStore()
        http = await self._async_create_http()
        try:
            auth = AuthManager(
                http=http,
                store=store,
                sberid_tokens=self._sberid_tokens,
                on_sberid_refreshed=self._async_remember_sberid_tokens,
            )
            await _async_probe_gateway(http, auth)
        except Exception as err:
            error = _flow_error(err, "Sber smart home check")
            if error == "invalid_auth":
                self._sberid_tokens = None
            return error
        finally:
            await http.aclose()
        self._companion_tokens = await store.load()
        return None

    async def _async_remember_sberid_tokens(self, tokens: SberIdTokens) -> None:
        """Сохранить во flow токены Сбер ID, обновлённые во время проверки.

        refresh_token Сбера одноразовый: без этого в запись попал бы уже
        использованный токен.
        """
        self._sberid_tokens = tokens

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

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle reauthentication — диспатч на тот же flow что использовался изначально."""
        # Csafront entries: предзаполним phone для удобства.
        method = entry_data.get(CONF_AUTH_METHOD)
        if method == AUTH_METHOD_CSAFRONT:
            csaf = entry_data.get(CONF_CSAFRONT_TOKENS) or {}
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
            # Фронтенд перечитал flow на внешнем шаге — отдаём тот же шаг.
            return await self._start_external_auth("reauth_authorize")

        # Called by SberAuthCallbackView after successful auth
        return self.async_external_step_done(next_step_id="finish")


async def _async_close_clients(client: SberAPI | None, http: httpx.AsyncClient | None) -> None:
    """Закрыть httpx-клиенты flow, оставшиеся после его удаления."""
    if client is not None:
        await client.aclose()
    if http is not None:
        await http.aclose()


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
    """Handle options for SberHome.

    `automatic_reload` выключен намеренно. Базовый класс сам перезагружает entry
    после сохранения, но HA запрещает это делать интеграциям с update-listener'ом
    («It's not allowed to use this class if the integration uses config entry
    update listeners»), а листенер у нас есть — `__init__.py`, `add_update_listener`.
    Перезагрузку обеспечивает он же: options меняются, листенер срабатывает.
    """

    automatic_reload = False

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Сохраняем поверх существующих options, а не вместо них. Форма знает
            # только про scan_interval, а в options живёт ещё и выбор устройств.
            # `async_create_entry(data=user_input)` заменял бы словарь целиком, и
            # сохранение интервала опроса стирало бы выбор пользователя.
            return self.async_create_entry(data={**self.config_entry.options, **user_input})

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema(
                    {
                        vol.Required(
                            CONF_SCAN_INTERVAL,
                            default=DEFAULT_SCAN_INTERVAL,
                        ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
                        vol.Required(
                            CONF_DEVTOOLS_BUFFER_SIZE,
                            default=DEFAULT_DEVTOOLS_BUFFER_SIZE,
                        ): vol.All(int, vol.Range(**SETTINGS_LIMITS[CONF_DEVTOOLS_BUFFER_SIZE])),
                        vol.Required(
                            CONF_COMMAND_TIMEOUT,
                            default=DEFAULT_COMMAND_TIMEOUT,
                        ): vol.All(
                            vol.Coerce(float), vol.Range(**SETTINGS_LIMITS[CONF_COMMAND_TIMEOUT])
                        ),
                    }
                ),
                self.config_entry.options,
            ),
        )
