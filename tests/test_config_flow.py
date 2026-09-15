"""Tests for the SberHome config flow.

Flow проходит через настоящий менеджер flow Home Assistant, а облако Сбера
подменено на уровне HTTP (``httpx.MockTransport``): вход по Сбер ID и по SMS,
обмен токенов и проверочный запрос к шлюзу выполняет код aiosber. Фикстура
``cloud`` запоминает каждый httpx-клиент, созданный flow, и после теста
проверяет, что все они закрыты.
"""

from __future__ import annotations

import base64
import json
from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers.network import NoURLAvailableError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome._ha_token_store import (
    CONF_COMPANION_TOKENS,
    CONF_CSAFRONT_TOKENS,
)
from custom_components.sberhome.aiosber.const import (
    AUTH_METHOD_CSAFRONT,
    AUTH_METHOD_SBERID,
    COMPANION_BASE_URL,
    COMPANION_TOKEN_PATH,
    CSAFRONT_AUTHENTICATE_URL,
    CSAFRONT_SMARTHOME_TOKEN_URL,
    CSAFRONT_VERIFY_URL,
    GATEWAY_BASE_URL,
    TOKEN_ENDPOINT,
)
from custom_components.sberhome.auth_state import pending_auth_flows
from custom_components.sberhome.config_flow import (
    ConfigFlow,
    SberHomeOptionsFlow,
    _normalize_phone,
)
from custom_components.sberhome.const import (
    CONF_AUTH_METHOD,
    CONF_COMMAND_TIMEOUT,
    CONF_DEVTOOLS_BUFFER_SIZE,
    CONF_ENABLED_DEVICE_IDS,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    DOMAIN,
    MAX_SCAN_INTERVAL,
)

PHONE = "78001234567"
SUB = "account-sub"
COMPANION_TOKEN = "companion-access"
SMART_HOME_TOKEN = "smart-home-token"


def _make_token_with_sub(sub: str | None) -> dict:
    """Сконструировать token dict с id_token содержащим sub claim."""

    def b64(obj: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

    payload: dict = {"aud": "client"}
    if sub is not None:
        payload["sub"] = sub
    id_token = f"{b64({'alg': 'RS256'})}.{b64(payload)}.fake-sig"
    return {"access_token": "at", "refresh_token": "rt", "id_token": id_token}


Reply = httpx.Response | Exception | Callable[[httpx.Request], httpx.Response]

_AsyncClient = httpx.AsyncClient
"""Настоящий класс клиента: в тестах ``httpx.AsyncClient`` подменён фабрикой."""


class FakeSberCloud:
    """Облако Сбера для flow: SMS-коды, токены, companion и шлюз.

    ``fail(route, *replies)`` ставит ответы в очередь маршрута: сначала
    отдаются они, затем штатный ответ. Ответ — ``httpx.Response``, исключение
    (бросается транспортом) или функция от запроса.
    """

    def __init__(self) -> None:
        self.sub: str | None = SUB
        self.codes: dict[str, str] = {}
        self.sent = 0
        self.clients: list[httpx.AsyncClient] = []
        self.requests: list[httpx.Request] = []
        self._queued: dict[str, list[Reply]] = {}
        self._issued = 0

    # --- управление ---------------------------------------------------------

    def fail(self, route: str, *replies: Reply) -> None:
        self._queued.setdefault(route, []).extend(replies)

    def expire_codes(self) -> None:
        self.codes.clear()

    @property
    def last_code(self) -> str:
        return f"{self.sent:06d}"

    def calls(self, route: str) -> list[httpx.Request]:
        return [r for r in self.requests if self._route(r) == route]

    def client_factory(self, *args: Any, **kwargs: Any) -> httpx.AsyncClient:
        client = _AsyncClient(transport=httpx.MockTransport(self._handle))
        self.clients.append(client)
        return client

    # --- транспорт ----------------------------------------------------------

    @staticmethod
    def _route(request: httpx.Request) -> str:
        url = str(request.url).split("?")[0]
        if url == CSAFRONT_AUTHENTICATE_URL:
            return "send_otp"
        if url == CSAFRONT_VERIFY_URL:
            return "verify"
        if url == TOKEN_ENDPOINT:
            grant = parse_qs(request.content.decode())["grant_type"][0]
            return "refresh" if grant == "refresh_token" else "token"
        if url == CSAFRONT_SMARTHOME_TOKEN_URL:
            return "smart_home_token"
        if url == COMPANION_BASE_URL + COMPANION_TOKEN_PATH:
            return "companion"
        if url == f"{GATEWAY_BASE_URL}/device_groups":
            return "gateway"
        raise AssertionError(f"unexpected request {request.method} {url}")

    def _handle(self, request: httpx.Request) -> httpx.Response:
        route = self._route(request)
        self.requests.append(request)
        if queue := self._queued.get(route):
            reply = queue.pop(0)
            if isinstance(reply, Exception):
                raise reply
            if isinstance(reply, httpx.Response):
                return reply
            return reply(request)
        return getattr(self, f"_ok_{route}")(request)

    def _ok_send_otp(self, request: httpx.Request) -> httpx.Response:
        self.sent += 1
        ouid = f"ouid-{self.sent}"
        self.codes[ouid] = self.last_code
        return httpx.Response(200, json={"ouid": ouid})

    def _ok_verify(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        ouid = body["identifier"]["data"]["value"]
        otp = body["authenticator"]["data"]["value"]
        if self.codes.get(ouid) != otp:
            return httpx.Response(400, json={"error": "wrong or expired code"})
        del self.codes[ouid]
        return httpx.Response(200, json={"authcode": f"authcode-{ouid}"})

    def _tokens(self) -> dict[str, Any]:
        self._issued += 1
        tokens = _make_token_with_sub(self.sub)
        tokens.update(
            access_token=f"access-{self._issued}",
            refresh_token=f"refresh-{self._issued}",
            expires_in=3600,
        )
        return tokens

    def _ok_token(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self._tokens())

    def _ok_refresh(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=self._tokens())

    def _ok_smart_home_token(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token": SMART_HOME_TOKEN})

    def _ok_companion(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"access_token": COMPANION_TOKEN, "expires_in": 86400})

    def _ok_gateway(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": [{"id": "home-1", "name": "Дом"}]})


@pytest.fixture
async def cloud(hass: HomeAssistant, sberhome_integration: None) -> AsyncIterator[FakeSberCloud]:
    """Облако Сбера; после теста все httpx-клиенты flow должны быть закрыты.

    Незавершённые flow прерываются так же, как при закрытии диалога.
    """
    fake = FakeSberCloud()
    with (
        patch(
            "custom_components.sberhome.config_flow.httpx.AsyncClient",
            side_effect=fake.client_factory,
        ),
        patch("custom_components.sberhome.config_flow.async_init_ssl", AsyncMock()),
        patch(
            "custom_components.sberhome.config_flow.get_url",
            return_value="http://ha.local:8123",
        ),
        patch("custom_components.sberhome.async_setup_entry", AsyncMock(return_value=True)),
        patch("custom_components.sberhome.async_unload_entry", AsyncMock(return_value=True)),
    ):
        yield fake
        for flow in hass.config_entries.flow.async_progress_by_handler(DOMAIN):
            hass.config_entries.flow.async_abort(flow["flow_id"])
        # Выгрузка — пока async_unload_entry подменён (иначе её сделает hass
        # при остановке, уже без подмены).
        for entry in hass.config_entries.async_entries(DOMAIN):
            await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    assert [c for c in fake.clients if not c.is_closed] == []
    assert pending_auth_flows == {}


async def _start(hass: HomeAssistant, method: str) -> dict[str, Any]:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": method}
    )


async def _sberid_login(hass: HomeAssistant, result: dict[str, Any]) -> dict[str, Any]:
    """Пройти внешний шаг Сбер ID так, как это делает страница авторизации."""
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    flow_id = result["flow_id"]
    pending = pending_auth_flows[flow_id]
    state = parse_qs(urlparse(pending.auth_url).query)["state"][0]
    assert await pending.client.authorize_by_url(f"companionapp://host?code=abc&state={state}")
    result = await hass.config_entries.flow.async_configure(flow_id, {})
    assert result["type"] is FlowResultType.EXTERNAL_STEP_DONE
    return await hass.config_entries.flow.async_configure(flow_id)


async def _sms_login(hass: HomeAssistant, result: dict[str, Any], cloud: FakeSberCloud) -> dict:
    assert result["step_id"] == "sms_phone"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "+7 (800) 123-45-67"}
    )
    assert result["step_id"] == "sms_otp"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )


def _suggested(schema: Any, field: str) -> Any:
    """Подсказанное значение поля формы (``add_suggested_values_to_schema``)."""
    (key,) = (k for k in schema.schema if str(k) == field)
    return (key.description or {}).get("suggested_value")


def _sberid_entry(hass: HomeAssistant, unique_id: str | None = SUB) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={CONF_AUTH_METHOD: AUTH_METHOD_SBERID, CONF_TOKEN: {"access_token": "old"}},
        options={CONF_ENABLED_DEVICE_IDS: ["dev-1"]},
    )
    entry.add_to_hass(hass)
    return entry


def _sms_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"csafront:{PHONE}",
        title=f"SberHome (SMS · {PHONE})",
        data={
            CONF_AUTH_METHOD: AUTH_METHOD_CSAFRONT,
            CONF_CSAFRONT_TOKENS: {"smart_home_token": "old", "phone": PHONE},
        },
    )
    entry.add_to_hass(hass)
    return entry


# --- меню -------------------------------------------------------------------


async def test_user_step_offers_both_login_methods(hass: HomeAssistant, cloud) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["sberid", "sms"]
    assert cloud.clients == []


# --- Сбер ID ----------------------------------------------------------------


async def test_sberid_flow_checks_cloud_and_creates_entry(
    hass: HomeAssistant, cloud, hass_client_no_auth
) -> None:
    result = await _start(hass, "sberid")

    assert result["type"] is FlowResultType.EXTERNAL_STEP
    parsed = urlparse(result["url"])
    assert (parsed.scheme, parsed.netloc, parsed.path) == (
        "http",
        "ha.local:8123",
        "/auth/sberhome",
    )
    # Ссылка на Сбер ID не передаётся через query (её можно подменить).
    assert parse_qs(parsed.query) == {"flow_id": [result["flow_id"]]}
    # Страница авторизации зарегистрирована и открывается по этой ссылке.
    page = await (await hass_client_no_auth()).get(f"{parsed.path}?{parsed.query}")
    assert page.status == 200

    result = await _sberid_login(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "SberHome"
    assert result["result"].unique_id == SUB
    assert result["options"] == {CONF_ENABLED_DEVICE_IDS: []}
    data = result["data"]
    assert data[CONF_AUTH_METHOD] == AUTH_METHOD_SBERID
    assert data[CONF_TOKEN]["refresh_token"] == "refresh-1"
    assert data[CONF_COMPANION_TOKENS]["access_token"] == COMPANION_TOKEN
    # Проверка облака: обмен на companion-токен и запрос к шлюзу с ним.
    assert len(cloud.calls("companion")) == 1
    (gateway,) = cloud.calls("gateway")
    assert gateway.headers["X-AUTH-jwt"] == COMPANION_TOKEN
    assert gateway.url.params["group_type"] == "HOME"


async def test_sberid_refetching_external_step_keeps_login_link(hass: HomeAssistant, cloud) -> None:
    """Фронтенд перечитывает flow без данных — ссылка и клиент те же."""
    result = await _start(hass, "sberid")
    pending = pending_auth_flows[result["flow_id"]]

    again = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert again["type"] is FlowResultType.EXTERNAL_STEP
    assert again["url"] == result["url"]
    assert pending_auth_flows[result["flow_id"]] is pending
    assert len(cloud.clients) == 1


async def test_sberid_expired_login_starts_over(hass: HomeAssistant, cloud) -> None:
    """Просроченный вход убран сборщиком — перечитывание даёт новый вход."""
    result = await _start(hass, "sberid")
    pending_auth_flows[result["flow_id"]].created_at -= 3600

    again = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert again["type"] is FlowResultType.EXTERNAL_STEP
    assert len(cloud.clients) == 2
    assert cloud.clients[0].is_closed
    assert (await _sberid_login(hass, again))["type"] is FlowResultType.CREATE_ENTRY


async def test_sberid_without_ha_url_aborts_without_leaking_client(
    hass: HomeAssistant, cloud
) -> None:
    with patch("custom_components.sberhome.config_flow.get_url", side_effect=NoURLAvailableError):
        result = await _start(hass, "sberid")

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_url_available"
    assert [c for c in cloud.clients if not c.is_closed] == []


async def test_sberid_login_without_token_aborts(hass: HomeAssistant, cloud) -> None:
    """Колбэк продвинул шаг, но обмен кода не дал токенов."""
    result = await _start(hass, "sberid")

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "invalid_auth"
    assert cloud.calls("gateway") == []


async def test_sberid_user_closes_dialog_on_external_step(hass: HomeAssistant, cloud) -> None:
    result = await _start(hass, "sberid")
    assert not cloud.clients[0].is_closed

    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()

    assert cloud.clients[0].is_closed
    assert result["flow_id"] not in pending_auth_flows


async def test_sberid_cloud_unavailable_then_retry_succeeds(hass: HomeAssistant, cloud) -> None:
    cloud.fail("gateway", httpx.ConnectError("boom"), httpx.Response(503, text="down"))
    result = await _sberid_login(hass, await _start(hass, "sberid"))

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sberid_retry"
    assert result["errors"] == {"base": "cannot_connect"}
    assert hass.config_entries.async_entries(DOMAIN) == []

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Повтор — только проверка облака, без нового входа через Сбер ID.
    assert len(cloud.calls("token")) == 1
    assert len(cloud.calls("gateway")) == 3


async def test_sberid_rejected_credentials_open_new_login(hass: HomeAssistant, cloud) -> None:
    cloud.fail(
        "companion",
        httpx.Response(401, json={"error": "denied"}),
    )
    cloud.fail("refresh", httpx.Response(400, json={"error": "invalid_grant"}))
    result = await _sberid_login(hass, await _start(hass, "sberid"))

    assert result["step_id"] == "sberid_retry"
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    assert result["step_id"] == "sberid"

    result = await _sberid_login(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(cloud.calls("token")) == 2


async def test_sberid_unexpected_error_is_unknown(hass: HomeAssistant, cloud) -> None:
    cloud.fail("gateway", httpx.Response(200, json={"result": {"not": "a list"}}))
    result = await _sberid_login(hass, await _start(hass, "sberid"))

    assert result["errors"] == {"base": "unknown"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_sberid_tokens_rotated_during_check_are_stored(hass: HomeAssistant, cloud) -> None:
    """refresh_token Сбера одноразовый: в запись попадает новый."""
    cloud.fail("companion", httpx.Response(401, json={"error": "expired"}))
    result = await _sberid_login(hass, await _start(hass, "sberid"))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(cloud.calls("refresh")) == 1
    assert result["data"][CONF_TOKEN]["refresh_token"] == "refresh-2"


async def test_sberid_account_is_not_added_twice(hass: HomeAssistant, cloud) -> None:
    """Параллельный вход прерывается, как только первый создал запись."""
    first = await _start(hass, "sberid")
    second = await _start(hass, "sberid")

    assert (await _sberid_login(hass, first))["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []
    assert second["flow_id"] not in pending_auth_flows
    assert all(client.is_closed for client in cloud.clients)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_sberid_ignored_account_can_be_set_up(hass: HomeAssistant, cloud) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=SUB, source=SOURCE_IGNORE).add_to_hass(hass)

    result = await _sberid_login(hass, await _start(hass, "sberid"))

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_sberid_token_without_account_id(hass: HomeAssistant, cloud) -> None:
    cloud.sub = None

    result = await _sberid_login(hass, await _start(hass, "sberid"))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id is None


# --- Сбер ID: reauth --------------------------------------------------------


async def _reauth(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"
    return await hass.config_entries.flow.async_configure(result["flow_id"], {})


async def test_sberid_reauth_same_account(hass: HomeAssistant, cloud) -> None:
    entry = _sberid_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["description_placeholders"]["method"] == "Sber ID"

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["step_id"] == "reauth_authorize"
        result = await _sberid_login(hass, result)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN]["refresh_token"] == "refresh-1"
    assert entry.data[CONF_COMPANION_TOKENS]["access_token"] == COMPANION_TOKEN
    assert entry.options == {CONF_ENABLED_DEVICE_IDS: ["dev-1"]}
    reload.assert_called_once_with(entry.entry_id)
    assert len(cloud.calls("gateway")) == 1


async def test_sberid_reauth_other_account_aborts(hass: HomeAssistant, cloud) -> None:
    entry = _sberid_entry(hass, unique_id="another-account")

    result = await _sberid_login(hass, await _reauth(hass, entry))

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert entry.data[CONF_TOKEN] == {"access_token": "old"}
    assert cloud.calls("gateway") == []


async def test_sberid_reauth_without_account_id_aborts(hass: HomeAssistant, cloud) -> None:
    """Токен без id_token не подтверждает, что аккаунт тот же."""
    entry = _sberid_entry(hass)
    cloud.sub = None

    result = await _sberid_login(hass, await _reauth(hass, entry))

    assert result["reason"] == "wrong_account"


async def test_sberid_reauth_entry_without_unique_id_gets_one(hass: HomeAssistant, cloud) -> None:
    entry = _sberid_entry(hass, unique_id=None)

    result = await _sberid_login(hass, await _reauth(hass, entry))

    assert result["reason"] == "reauth_successful"
    assert entry.unique_id == SUB


async def test_sberid_reauth_rejected_then_new_login(hass: HomeAssistant, cloud) -> None:
    entry = _sberid_entry(hass)
    cloud.fail("gateway", httpx.Response(401))
    cloud.fail("companion", httpx.Response(200, json={"access_token": "first"}))
    cloud.fail("refresh", httpx.Response(400, json={"error": "invalid_grant"}))
    cloud.fail("companion", httpx.Response(401))

    result = await _sberid_login(hass, await _reauth(hass, entry))
    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    assert result["step_id"] == "reauth_authorize"

    # Фронтенд перечитал flow на внешнем шаге reauth.
    again = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert again["url"] == result["url"]

    result = await _sberid_login(hass, again)
    assert result["reason"] == "reauth_successful"


# --- SMS --------------------------------------------------------------------


async def test_sms_flow_checks_cloud_and_creates_entry(hass: HomeAssistant, cloud) -> None:
    result = await _start(hass, "sms")
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sms_phone"
    assert result["description_placeholders"] == {"example_phone": PHONE}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "8 (800) 123-45-67"}
    )
    assert result["step_id"] == "sms_otp"
    assert result["description_placeholders"] == {"phone": PHONE}
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": f" {cloud.last_code} "}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == f"SberHome (SMS · {PHONE})"
    assert result["result"].unique_id == f"csafront:{PHONE}"
    assert result["options"] == {CONF_ENABLED_DEVICE_IDS: []}
    tokens = result["data"][CONF_CSAFRONT_TOKENS]
    assert result["data"][CONF_AUTH_METHOD] == AUTH_METHOD_CSAFRONT
    assert tokens["smart_home_token"] == SMART_HOME_TOKEN
    assert tokens["csafront_refresh_token"] == "refresh-1"
    assert tokens["phone"] == PHONE
    (gateway,) = cloud.calls("gateway")
    assert gateway.headers["X-AUTH-jwt"] == SMART_HOME_TOKEN
    assert len(cloud.clients) == 1


async def test_sms_invalid_phone(hass: HomeAssistant, cloud) -> None:
    result = await _start(hass, "sms")

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": "123"})

    assert result["step_id"] == "sms_phone"
    assert result["errors"] == {"phone": "invalid_phone"}
    assert cloud.calls("send_otp") == []
    assert (await _sms_login(hass, result, cloud))["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    "failure",
    [httpx.Response(500, text="oops"), httpx.ConnectError("no route")],
    ids=["rejected", "network"],
)
async def test_sms_send_failure_then_retry(hass: HomeAssistant, cloud, failure) -> None:
    cloud.fail("send_otp", failure)
    result = await _start(hass, "sms")

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})

    assert result["step_id"] == "sms_phone"
    assert result["errors"] == {"base": "send_otp_failed"}
    assert cloud.clients[0].is_closed
    # Номер остаётся в форме.
    assert _suggested(result["data_schema"], "phone") == PHONE
    assert (await _sms_login(hass, result, cloud))["type"] is FlowResultType.CREATE_ENTRY


async def test_sms_send_unexpected_error(hass: HomeAssistant, cloud) -> None:
    cloud.fail("send_otp", RuntimeError("bug"))
    result = await _start(hass, "sms")

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})

    assert result["errors"] == {"base": "unknown"}


async def test_sms_wrong_code_then_correct(hass: HomeAssistant, cloud) -> None:
    result = await _start(hass, "sms")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": "999999"})
    assert result["step_id"] == "sms_otp"
    assert result["errors"] == {"base": "invalid_otp"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"otp": "invalid_otp"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_sms_expired_code_resend(hass: HomeAssistant, cloud) -> None:
    result = await _start(hass, "sms")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})
    old_code = cloud.last_code
    cloud.expire_codes()

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": old_code})
    assert result["errors"] == {"base": "invalid_otp"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": old_code, "resend": True}
    )
    assert result["step_id"] == "sms_otp"
    assert result["errors"] == {}
    assert len(cloud.calls("send_otp")) == 2
    assert cloud.clients[0].is_closed

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_sms_resend_failure(hass: HomeAssistant, cloud) -> None:
    result = await _start(hass, "sms")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})
    code = cloud.last_code
    cloud.fail("send_otp", httpx.Response(502))

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"resend": True})
    assert result["errors"] == {"base": "send_otp_failed"}

    # Новый код не отправлен, старый сброшен вместе с попыткой.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": code})
    assert result["errors"] == {"base": "invalid_otp"}
    assert cloud.calls("verify") == []

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"resend": True})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (httpx.ReadTimeout("slow"), "cannot_connect"),
        (httpx.Response(500, text="oops"), "invalid_auth"),
        (RuntimeError("bug"), "unknown"),
    ],
    ids=["network", "rejected", "unexpected"],
)
async def test_sms_code_check_failure_keeps_code(
    hass: HomeAssistant, cloud, failure, error
) -> None:
    """Код не принят из-за сбоя, а не потому что неверный — его можно ввести снова."""
    cloud.fail("verify", failure)
    result = await _start(hass, "sms")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )
    assert result["errors"] == {"base": error}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("route", "failure", "error"),
    [
        ("token", httpx.Response(400, json={"error": "invalid_grant"}), "invalid_auth"),
        ("token", httpx.ConnectError("no route"), "cannot_connect"),
        ("smart_home_token", httpx.Response(503, text="down"), "cannot_connect"),
        ("smart_home_token", httpx.Response(403, text="denied"), "invalid_auth"),
    ],
)
async def test_sms_sign_in_failure_needs_new_code(
    hass: HomeAssistant, cloud, route, failure, error
) -> None:
    """Код уже обменян: после сбоя входа нужен новый код."""
    cloud.fail(route, failure)
    result = await _start(hass, "sms")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})
    code = cloud.last_code

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": code})
    assert result["errors"] == {"base": error}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"otp": code})
    assert result["errors"] == {"base": "invalid_otp"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"resend": True})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (httpx.Response(503, text="down"), "cannot_connect"),
        (httpx.Response(429, text="slow down"), "cannot_connect"),
        (httpx.Response(200, text="<html>"), "unknown"),
    ],
)
async def test_sms_cloud_check_failure_then_retry(
    hass: HomeAssistant, cloud, failure, error
) -> None:
    cloud.fail("gateway", failure)
    result = await _sms_login(hass, await _start(hass, "sms"), cloud)

    assert result["step_id"] == "sms_otp"
    assert result["errors"] == {"base": error}
    assert hass.config_entries.async_entries(DOMAIN) == []

    # Повтор — только проверка облака: код одноразовый и уже принят.
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(cloud.calls("verify")) == 1
    assert len(cloud.calls("gateway")) == 2


async def test_sms_cloud_rejects_credentials(hass: HomeAssistant, cloud) -> None:
    cloud.fail("gateway", httpx.Response(401))
    cloud.fail("refresh", httpx.Response(400, json={"error": "invalid_grant"}))
    result = await _sms_login(hass, await _start(hass, "sms"), cloud)

    assert result["errors"] == {"base": "invalid_auth"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["errors"] == {"otp": "invalid_otp"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"resend": True})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"otp": cloud.last_code}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_sms_tokens_rotated_during_check_are_stored(hass: HomeAssistant, cloud) -> None:
    cloud.fail("gateway", httpx.Response(401))
    result = await _sms_login(hass, await _start(hass, "sms"), cloud)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CSAFRONT_TOKENS]["csafront_refresh_token"] == "refresh-2"


async def test_sms_rotated_tokens_survive_failed_check(hass: HomeAssistant, cloud) -> None:
    cloud.fail("gateway", httpx.Response(401), httpx.Response(503))
    result = await _sms_login(hass, await _start(hass, "sms"), cloud)
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_CSAFRONT_TOKENS]["csafront_refresh_token"] == "refresh-2"
    assert len(cloud.calls("refresh")) == 1


async def test_sms_user_closes_dialog_on_code_form(hass: HomeAssistant, cloud) -> None:
    result = await _start(hass, "sms")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"phone": PHONE})
    assert not cloud.clients[0].is_closed

    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done()

    assert cloud.clients[0].is_closed


async def test_sms_same_phone_in_parallel_flows(hass: HomeAssistant, cloud) -> None:
    first = await _start(hass, "sms")
    second = await _start(hass, "sms")
    first = await hass.config_entries.flow.async_configure(first["flow_id"], {"phone": PHONE})

    result = await hass.config_entries.flow.async_configure(second["flow_id"], {"phone": PHONE})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_in_progress"
    assert len(cloud.calls("send_otp")) == 1


async def test_sms_account_is_not_added_twice(hass: HomeAssistant, cloud) -> None:
    """Параллельный вход по SMS прерывается, как только первый создал запись."""
    second = await _start(hass, "sms")
    second = await hass.config_entries.flow.async_configure(
        second["flow_id"], {"phone": "79990001122"}
    )
    assert second["step_id"] == "sms_otp"

    result = await _sms_login(hass, await _start(hass, "sms"), cloud)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []
    assert all(client.is_closed for client in cloud.clients)
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


# --- SMS: reauth ------------------------------------------------------------


async def test_sms_reauth_same_phone(hass: HomeAssistant, cloud) -> None:
    entry = _sms_entry(hass)
    result = await entry.start_reauth_flow(hass)
    assert result["description_placeholders"]["method"] == "SMS"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["step_id"] == "sms_phone"
    # Номер записи подставлен в форму.
    assert _suggested(result["data_schema"], "phone") == PHONE

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await _sms_login(hass, result, cloud)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_CSAFRONT_TOKENS]["smart_home_token"] == SMART_HOME_TOKEN
    reload.assert_called_once_with(entry.entry_id)


async def test_sms_reauth_other_phone_aborts_before_sms(hass: HomeAssistant, cloud) -> None:
    entry = _sms_entry(hass)
    result = await _reauth(hass, entry)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"phone": "79990001122"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert cloud.calls("send_otp") == []
    assert entry.data[CONF_CSAFRONT_TOKENS]["smart_home_token"] == "old"


# --- форма параметров -------------------------------------------------------


async def test_options_flow(hass: HomeAssistant, cloud) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_METHOD: AUTH_METHOD_SBERID},
        options={CONF_SCAN_INTERVAL: 60, CONF_ENABLED_DEVICE_IDS: ["dev-1"]},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert _suggested(result["data_schema"], CONF_SCAN_INTERVAL) == 60

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: MAX_SCAN_INTERVAL + 1}
        )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 120, CONF_DEVTOOLS_BUFFER_SIZE: 300, CONF_COMMAND_TIMEOUT: 15},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Форма не знает про выбор устройств — он не стирается.
    assert entry.options == {
        CONF_SCAN_INTERVAL: 120,
        CONF_DEVTOOLS_BUFFER_SIZE: 300,
        CONF_COMMAND_TIMEOUT: 15.0,
        CONF_ENABLED_DEVICE_IDS: ["dev-1"],
    }


def test_options_flow_does_not_self_reload() -> None:
    """HA запрещает автоперезагрузку из options flow при наличии update-listener'а.

    Листенер у интеграции есть (`__init__.py`, add_update_listener), поэтому
    базовый `OptionsFlowWithReload` с `automatic_reload = True` — неподдерживаемая
    комбинация. Перезагрузку делает сам листенер на изменение options.
    """
    assert SberHomeOptionsFlow.automatic_reload is False


# --- тексты -----------------------------------------------------------------


def test_every_form_field_is_described_in_every_language() -> None:
    """Правило config-flow: у каждого поля каждой формы есть пояснение."""
    from pathlib import Path

    base = Path(__file__).resolve().parents[1] / "custom_components" / "sberhome"
    fields = {
        ("config", "sms_phone"): {"phone"},
        ("config", "sms_otp"): {"otp", "resend"},
        ("options", "init"): {CONF_SCAN_INTERVAL, CONF_DEVTOOLS_BUFFER_SIZE, CONF_COMMAND_TIMEOUT},
    }
    for path in [base / "strings.json", *sorted((base / "translations").glob("*.json"))]:
        strings = json.loads(path.read_text(encoding="utf-8"))
        for (section, step), keys in fields.items():
            texts = strings[section]["step"][step]
            assert set(texts["data"]) == keys, (path.name, step)
            assert set(texts["data_description"]) == keys, (path.name, step)
            assert all(texts["data_description"].values()), (path.name, step)
        config = strings["config"]
        assert config["step"]["sberid_retry"]["description"], path.name
        for error in ("cannot_connect", "invalid_auth", "unknown", "invalid_otp"):
            assert config["error"][error], (path.name, error)


# --- чистые функции ---------------------------------------------------------


def test_extract_sub_returns_claim_from_id_token() -> None:
    assert ConfigFlow._extract_sub(_make_token_with_sub("user-7777")) == "user-7777"


def test_extract_sub_returns_none_when_no_id_token() -> None:
    assert ConfigFlow._extract_sub({"access_token": "at"}) is None
    assert ConfigFlow._extract_sub({"access_token": "at", "id_token": None}) is None
    assert ConfigFlow._extract_sub({"access_token": "at", "id_token": ""}) is None


def test_extract_sub_returns_none_on_invalid_jwt() -> None:
    assert ConfigFlow._extract_sub({"id_token": "not-a-jwt"}) is None
    assert ConfigFlow._extract_sub({"id_token": "a.b.c.d"}) is None


def test_extract_sub_returns_none_when_sub_missing() -> None:
    assert ConfigFlow._extract_sub(_make_token_with_sub(None)) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("78001234567", "78001234567"),
        ("88001234567", "78001234567"),
        ("+7 (800) 123-45-67", "78001234567"),
        ("8001234567", "78001234567"),
        ("hello", None),
        ("", None),
        ("123", None),
        ("1234567890123456", None),
    ],
)
def test_normalize_phone(raw: str, expected: str | None) -> None:
    assert _normalize_phone(raw) == expected
