"""WebSocket клиент для `wss://ws.iot.sberdevices.ru`.

Подписка на real-time обновления state/event. Реализован как абстракция над
WebSocket-библиотекой через DI: фабрика подключения принимается параметром.

По умолчанию используется библиотека `websockets` (lazy import при первом
connect). HA может подключить свой factory на основе `aiohttp.ClientSession.ws_connect`.

Архитектура:

    AuthManager → access_token()
            │
            ▼
    WebSocketClient.run() ──────── factory(url, headers) ──► WebSocketProtocol
            │                                                     │
            │                                              recv() / send() / close()
            ▼
    SocketMessageDto  ────►  callback(msg)  ─── topic, payload — продакшн-логика
                                          (HA coordinator подписывается)

Жизненный цикл:
- `WebSocketClient.run()` — бесконечный цикл `connect → recv loop → reconnect on error`.
  Завершается только по `stop()` или unhandled exception.
- При 401 на handshake — вызов `auth.force_refresh()` и retry с backoff.
- Backoff экспоненциальный: 1, 2, 4, 8, 16, 32 (cap), затем 60s.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from ..auth.manager import AuthManager
from ..const import WEBSOCKET_BASE_URL
from ..dto import SocketMessageDto, Topic
from ..exceptions import AuthError, NetworkError, SberError

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Protocol-уровень: контракт WebSocket-объекта, нужный нам
# ---------------------------------------------------------------------------


class WebSocketProtocol(Protocol):
    """Минимальный API WebSocket-соединения, нужный WebSocketClient.

    Совместимо с `websockets.legacy.client.WebSocketClientProtocol`,
    `websockets.ClientConnection` (modern API), `aiohttp.ClientWebSocketResponse`.
    Адаптеры для каждой реализации можно сделать тонкими wrappers.
    """

    async def recv(self) -> str | bytes: ...
    async def send(self, data: str | bytes) -> None: ...
    async def close(self) -> None: ...


WebSocketFactory = Callable[[str, dict[str, str]], Awaitable[WebSocketProtocol]]
"""Callable: `factory(url, headers) → WebSocketProtocol`.

Headers содержит `Authorization: Bearer <companion_token>`.
"""

MessageCallback = Callable[[SocketMessageDto], Awaitable[None] | None]
"""Callback на каждое входящее WS-сообщение."""


# ---------------------------------------------------------------------------
# Default factory: lazy import websockets
# ---------------------------------------------------------------------------


async def default_websockets_factory(
    url: str, headers: dict[str, str]
) -> WebSocketProtocol:
    """Default WebSocket factory using the `websockets` library (lazy-imported).

    Требует `pip install websockets>=12.0`. Подключается с заголовками auth.
    """
    try:
        import websockets  # type: ignore[import-not-found]
    except ImportError as err:
        raise SberError(
            "websockets library required for WebSocketClient. "
            "Install via `pip install websockets`."
        ) from err

    return await websockets.connect(  # type: ignore[no-any-return]
        url,
        additional_headers=list(headers.items()),
    )


# ---------------------------------------------------------------------------
# WebSocketClient
# ---------------------------------------------------------------------------


class WebSocketClient:
    """Async WebSocket client with auto-reconnect and per-topic dispatch.

    Args:
        auth: AuthManager (для подписи handshake актуальным токеном).
        callback: вызывается на каждое входящее `SocketMessageDto`.
            Может быть sync или async. Исключения внутри callback логируются
            и не ломают WS loop.
        factory: фабрика создания WebSocket-соединения. Default — `websockets` lib.
            Override для тестов или для использования HA aiohttp.
        url: base WebSocket URL (default — prod).
        backoff_initial: первый delay reconnect, секунды.
        backoff_max: максимальный delay reconnect.
        backoff_multiplier: множитель при каждом провале (по умолчанию 2.0).
    """

    def __init__(
        self,
        auth: AuthManager,
        callback: MessageCallback,
        *,
        factory: WebSocketFactory = default_websockets_factory,
        url: str = WEBSOCKET_BASE_URL,
        backoff_initial: float = 1.0,
        backoff_max: float = 60.0,
        backoff_multiplier: float = 2.0,
    ) -> None:
        self._auth = auth
        self._callback = callback
        self._factory = factory
        self._url = url
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._backoff_multiplier = backoff_multiplier

        self._stop_event = asyncio.Event()
        self._connection: WebSocketProtocol | None = None
        self._connected_event = asyncio.Event()

    # ----- Public API -----
    @property
    def is_connected(self) -> bool:
        return self._connected_event.is_set()

    async def wait_until_connected(self, timeout: float | None = None) -> None:
        """Ждать первого успешного connect (для интеграционных тестов)."""
        await asyncio.wait_for(self._connected_event.wait(), timeout=timeout)

    async def run(self) -> None:
        """Запустить infinite reconnect loop. Завершается только по `stop()`.

        Используется как long-running task: `task = asyncio.create_task(client.run())`.
        """
        backoff = self._backoff_initial
        while not self._stop_event.is_set():
            try:
                await self._connect_and_receive()
                # Чистое завершение recv (сервер закрыл соединение) — reconnect без backoff
                backoff = self._backoff_initial
            except AuthError:
                # Critical: refresh не помог. Останавливаемся, callback должен решить дальше.
                _LOGGER.error("WebSocket auth failed, stopping")
                raise
            except SberError as err:
                _LOGGER.warning("WebSocket error: %s; reconnect in %.1fs", err, backoff)
            except asyncio.CancelledError:
                _LOGGER.debug("WebSocket cancelled")
                raise
            except Exception:
                _LOGGER.exception("Unexpected WebSocket error; reconnect in %.1fs", backoff)

            self._connected_event.clear()
            if self._stop_event.is_set():
                break
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                # stop_event сработал → выходим
                break
            except TimeoutError:
                pass  # backoff истёк → новая попытка
            backoff = min(backoff * self._backoff_multiplier, self._backoff_max)

    async def stop(self) -> None:
        """Закрыть соединение и остановить reconnect loop."""
        self._stop_event.set()
        conn = self._connection
        if conn is not None:
            try:
                await conn.close()
            except Exception:  # noqa: BLE001 — best-effort close
                _LOGGER.debug("Error closing WS connection", exc_info=True)
        self._connected_event.clear()

    # ----- Internal -----
    async def _connect_and_receive(self) -> None:
        """Один цикл: получить токен → handshake → recv loop.

        Sber WS поддерживает оба формата auth-header: стандартный
        `Authorization: Bearer <token>` (как описано в APK-реверсе) ИЛИ
        gateway-style `X-AUTH-jwt: <token>` (как в REST-транспорте).

        Стратегия: пробуем Bearer, при handshake-ошибке — fallback на X-AUTH-jwt.
        Логируем DEBUG, какой путь сработал, для будущей оптимизации.
        """
        token = await self._auth.access_token()
        primary_headers = {"Authorization": f"Bearer {token}"}
        fallback_headers = {"X-AUTH-jwt": token}
        conn: WebSocketProtocol | None = None
        primary_err: Exception | None = None
        try:
            conn = await self._factory(self._url, primary_headers)
            _LOGGER.debug("WS handshake OK with Authorization: Bearer")
        except Exception as err:
            primary_err = err
            _LOGGER.debug(
                "WS handshake with Authorization: Bearer failed: %s; trying X-AUTH-jwt",
                err,
            )
            try:
                conn = await self._factory(self._url, fallback_headers)
                _LOGGER.debug("WS handshake OK with X-AUTH-jwt fallback")
            except Exception as fallback_err:
                # Оба варианта упали — это либо network, либо реально невалидный токен.
                # Различить нельзя без парсинга exception, поэтому маппим в NetworkError —
                # 401 на REST-уровне поднимется AuthError'ом и инициирует reauth.
                raise NetworkError(
                    f"WS connect failed: bearer={primary_err}; jwt={fallback_err}"
                ) from fallback_err

        assert conn is not None  # for mypy
        self._connection = conn
        self._connected_event.set()
        _LOGGER.debug("WebSocket connected to %s", self._url)
        try:
            while not self._stop_event.is_set():
                raw = await conn.recv()
                await self._handle_raw(raw)
        finally:
            self._connection = None
            with contextlib.suppress(Exception):
                await conn.close()

    async def _handle_raw(self, raw: str | bytes) -> None:
        """Парсинг raw → SocketMessageDto → callback."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            _LOGGER.warning("WS: ignored non-JSON message (%d chars)", len(raw))
            return

        if not isinstance(payload, dict):
            _LOGGER.warning("WS: ignored non-object message: %s", type(payload).__name__)
            return

        msg = SocketMessageDto.from_dict(payload)
        if msg is None:
            return

        try:
            result = self._callback(msg)
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            _LOGGER.exception(
                "WS callback failed for topic %s",
                msg.topic.value if msg.topic else "unknown",
            )


# ---------------------------------------------------------------------------
# Topic-router helper (опционально)
# ---------------------------------------------------------------------------


class TopicRouter:
    """Удобный helper: per-topic callbacks вместо single dispatcher.

    Использование:

        router = TopicRouter()
        router.on(Topic.DEVICE_STATE, on_device_state)
        router.on(Topic.DEVMAN_EVENT, on_event)

        ws_client = WebSocketClient(auth, callback=router)
        await ws_client.run()
    """

    def __init__(self) -> None:
        self._handlers: dict[Topic, list[MessageCallback]] = {}

    def on(self, topic: Topic, callback: MessageCallback) -> None:
        """Подписать callback на конкретный Topic. Можно несколько на один topic."""
        self._handlers.setdefault(topic, []).append(callback)

    async def __call__(self, msg: SocketMessageDto) -> None:
        topic = msg.topic
        if topic is None:
            return
        for cb in self._handlers.get(topic, ()):
            result = cb(msg)
            if asyncio.iscoroutine(result):
                await result


__all__ = [
    "MessageCallback",
    "TopicRouter",
    "WebSocketClient",
    "WebSocketFactory",
    "WebSocketProtocol",
    "default_websockets_factory",
]
