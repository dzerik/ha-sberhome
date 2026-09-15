"""Журнал при потере и возвращении связи с облаком Сбера: одна запись на событие.

Раньше каждый неудачный опрос писал предупреждение, пока облако недоступно, а
DataUpdateCoordinator Home Assistant вдобавок писал свою ошибку при первом
сбое. WebSocket-клиент так же предупреждал о каждой неудачной попытке
подключения и после серии сбоев пересоздавался следующим опросом — с новой
порцией предупреждений.

Проверяется поведение целиком: настоящий координатор и настоящий
HTTP-транспорт поверх подменённой сети, настоящий WebSocket-клиент поверх
подменённого соединения.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome import coordinator as coordinator_module
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.transport import HttpTransport, WebSocketClient
from custom_components.sberhome.api import SberAPI
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.coordinator import SberHomeCoordinator

LOGGER_NAME = "custom_components.sberhome"


class _Cloud:
    """Подменённое облако: ``ok``, ``down`` (нет сети), ``500`` или ``429``."""

    def __init__(self) -> None:
        self.mode = "ok"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.mode == "down":
            raise httpx.ConnectError("network is unreachable", request=request)
        if self.mode == "500":
            return httpx.Response(500, json={"message": "internal error"})
        if self.mode == "429":
            return httpx.Response(429, json={"message": "too many requests"})
        return httpx.Response(200, json={"result": []})


@pytest.fixture
def cloud() -> _Cloud:
    return _Cloud()


@pytest.fixture
async def coordinator(hass: HomeAssistant, cloud: _Cloud) -> AsyncIterator[SberHomeCoordinator]:
    """Настоящий координатор, чьи запросы уходят в подменённое облако."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id="availability-log", options={})
    entry.add_to_hass(hass)
    http = httpx.AsyncClient(transport=httpx.MockTransport(cloud))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="TOK", expires_in=86400))
    auth = AuthManager(http=http, store=store)
    coord = SberHomeCoordinator(
        hass,
        entry,
        AsyncMock(spec=SberAPI),
        HttpTransport(http=http, auth=auth),
        auth,
    )
    for poll in coord._background_polls():
        poll.disabled = True
    coord._start_ws_task = MagicMock()
    yield coord
    await http.aclose()


def _records(caplog: pytest.LogCaptureFixture, level: int) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name.startswith(LOGGER_NAME) and r.levelno == level]


def _problems(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records if r.name.startswith(LOGGER_NAME) and r.levelno >= logging.WARNING
    ]


# --- опрос облака -----------------------------------------------------------


@pytest.mark.parametrize("outage", ["down", "500"])
async def test_cloud_outage_logged_once_and_recovery_once(
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    caplog: pytest.LogCaptureFixture,
    outage: str,
) -> None:
    """Три неудачных опроса и возвращение: одна запись о сбое, одна о возврате."""
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    caplog.clear()

    cloud.mode = outage
    for _ in range(3):
        await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert len(_problems(caplog)) == 1
    assert _records(caplog, logging.INFO) == []

    cloud.mode = "ok"
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(_problems(caplog)) == 1
    assert len(_records(caplog, logging.INFO)) == 1

    # Следующий сбой — новый период недоступности, снова одна запись.
    caplog.clear()
    cloud.mode = outage
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert len(_problems(caplog)) == 1


@pytest.mark.parametrize("outage", ["500", "429"])
async def test_outage_logged_once_while_push_keeps_arriving(
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    caplog: pytest.LogCaptureFixture,
    outage: str,
) -> None:
    """Опрос падает, а WebSocket между опросами присылает push-обновления.

    Push выставляет ``last_update_success``, по которому DataUpdateCoordinator
    решает, писать ли ошибку: раньше каждый неудачный опрос писал новую
    ошибку, а о возвращении связи не писалось ничего.
    """
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    await coordinator.async_refresh()
    caplog.clear()

    cloud.mode = outage
    for _ in range(3):
        # Пауза после 429 не должна прятать повторные опросы от проверки.
        coordinator._rate_limited_until = 0.0
        await coordinator.async_refresh()
        assert coordinator.last_update_success is False
        coordinator._async_apply_push_data(coordinator.data or {})
        assert coordinator.last_update_success is True

    problems = _problems(caplog)
    assert len(problems) == 1
    assert problems[0].levelno == logging.WARNING
    assert _records(caplog, logging.INFO) == []

    cloud.mode = "ok"
    coordinator._rate_limited_until = 0.0
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True
    assert len(_problems(caplog)) == 1
    assert len(_records(caplog, logging.INFO)) == 1


async def test_refresh_skipped_inside_rate_limit_pause_is_not_logged_again(
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Опрос внутри паузы после 429 (облако не запрашивается) — без новой записи."""
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    await coordinator.async_refresh()
    cloud.mode = "429"
    await coordinator.async_refresh()
    assert coordinator.rate_limited
    coordinator._async_apply_push_data(coordinator.data or {})

    await coordinator.async_refresh()

    assert coordinator.last_update_success is False
    assert len(_problems(caplog)) == 1


async def test_first_refresh_during_setup_leaves_logging_to_setup(
    hass: HomeAssistant,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Сбой первого обновления при настройке записи: сообщает Home Assistant, не опрос.

    Запись о возвращении после такого сбоя тоже не пишется — потеря связи не
    записывалась.
    """
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    coordinator.config_entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    cloud.mode = "500"

    with pytest.raises(ConfigEntryNotReady):
        await coordinator.async_config_entry_first_refresh()

    assert _problems(caplog) == []
    cloud.mode = "ok"
    await coordinator.async_config_entry_first_refresh()
    assert _records(caplog, logging.INFO) == []


async def test_repeated_failures_are_still_visible_in_debug(
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Повторные сбои не пропадают бесследно: причина каждого — в отладочном журнале."""
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)
    cloud.mode = "down"
    await coordinator.async_refresh()
    caplog.clear()

    await coordinator.async_refresh()

    assert _problems(caplog) == []
    assert any("network is unreachable" in r.getMessage() for r in _records(caplog, logging.DEBUG))


# --- WebSocket --------------------------------------------------------------


class _BlockingWs:
    """Открытое соединение: ждёт закрытия, затем сообщает об обрыве."""

    def __init__(self) -> None:
        self._closed = asyncio.Event()

    async def recv(self) -> str:
        await self._closed.wait()
        raise ConnectionResetError("closed")

    async def send(self, data: str | bytes) -> None:
        return None

    async def close(self) -> None:
        self._closed.set()


class _WsServer:
    """Подменённый WebSocket-сервер: принимает или отвергает подключения."""

    def __init__(self) -> None:
        self.accept = True
        self.attempts = 0
        self.open: list[_BlockingWs] = []

    async def connect(self, url: str, headers: dict[str, str]) -> _BlockingWs:
        self.attempts += 1
        if not self.accept:
            raise OSError("connection refused")
        conn = _BlockingWs()
        self.open.append(conn)
        return conn

    async def drop_all(self) -> None:
        for conn in self.open:
            await conn.close()
        self.open.clear()


@pytest.fixture
def ws_server(coordinator: SberHomeCoordinator) -> AsyncIterator[_WsServer]:
    server = _WsServer()
    # Мгновенные переподключения; всё остальное — настоящий WebSocketClient.
    fast_client = functools.partial(WebSocketClient, backoff_initial=0.001, backoff_max=0.001)
    coordinator.async_request_refresh = AsyncMock()
    with (
        patch.object(coordinator_module, "async_get_clientsession"),
        patch.object(coordinator_module, "make_aiohttp_factory", return_value=server.connect),
        patch.object(coordinator_module, "WebSocketClient", fast_client),
    ):
        yield server


async def _wait_for(predicate, timeout: float = 2.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.001)


async def test_websocket_loss_logged_once_across_client_restarts(
    coordinator: SberHomeCoordinator,
    ws_server: _WsServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Обрыв, серия неудачных переподключений, перезапуск клиента опросом, возврат.

    Одно предупреждение о потере соединения и одна запись о возвращении.
    """
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)

    task = asyncio.create_task(coordinator._run_ws())
    await _wait_for(lambda: coordinator.ws_connected)
    assert _problems(caplog) == []
    assert _records(caplog, logging.INFO) == []

    # Соединение оборвалось, сервер не принимает: клиент сдаётся после серии
    # неудачных попыток, как при долгом отсутствии связи.
    ws_server.accept = False
    await ws_server.drop_all()
    await asyncio.wait_for(task, timeout=2)
    assert ws_server.attempts > 3
    assert len(_problems(caplog)) == 1
    assert "WebSocket" in _problems(caplog)[0].getMessage()

    # Следующий опрос запускает новый клиент — связи всё ещё нет.
    await asyncio.wait_for(coordinator._run_ws(), timeout=2)
    assert len(_problems(caplog)) == 1

    # Связь вернулась.
    ws_server.accept = True
    task = asyncio.create_task(coordinator._run_ws())
    await _wait_for(lambda: coordinator.ws_connected)
    assert len(_problems(caplog)) == 1
    restored = _records(caplog, logging.INFO)
    assert len(restored) == 1
    assert "WebSocket" in restored[0].getMessage()

    # Штатное закрытие сервером и мгновенное переподключение — не потеря связи.
    await ws_server.drop_all()
    await _wait_for(lambda: bool(ws_server.open))
    assert len(_problems(caplog)) == 1
    assert len(_records(caplog, logging.INFO)) == 1

    assert coordinator._ws_client is not None
    await coordinator._ws_client.stop()
    await asyncio.wait_for(task, timeout=2)


async def test_websocket_unexpected_error_logged_once_with_traceback(
    coordinator: SberHomeCoordinator,
    ws_server: _WsServer,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Неожиданная ошибка (дефект, а не сеть) — одна запись, но с трассировкой."""
    caplog.set_level(logging.DEBUG, logger=LOGGER_NAME)

    broken = AsyncMock(side_effect=RuntimeError("bug before handshake"))
    with patch.object(coordinator._auth_manager, "access_token", broken):
        await asyncio.wait_for(coordinator._run_ws(), timeout=2)
        await asyncio.wait_for(coordinator._run_ws(), timeout=2)

    problems = _problems(caplog)
    assert len(problems) == 1
    assert problems[0].exc_info is not None
