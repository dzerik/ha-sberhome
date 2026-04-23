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
from collections.abc import Awaitable, Callable, Iterable
from typing import Protocol
from urllib.parse import urlencode

from ..auth.manager import AuthManager
from ..const import (
    DEFAULT_WS_DEVICE_TYPE,
    DEFAULT_WS_TOPICS,
    WEBSOCKET_BASE_URL,
)
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


async def default_websockets_factory(url: str, headers: dict[str, str]) -> WebSocketProtocol:
    """Default WebSocket factory using the `websockets` library (lazy-imported).

    Требует `pip install websockets>=12.0`. Подключается с заголовками auth.
    """
    try:
        import websockets  # type: ignore[import-not-found]
    except ImportError as err:
        raise SberError(
            "websockets library required for WebSocketClient. Install via `pip install websockets`."
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
        topics: Iterable[str] = DEFAULT_WS_TOPICS,
        device_type: str = DEFAULT_WS_DEVICE_TYPE,
        home_ids: Iterable[str] | None = None,
        external_device_ids: Iterable[str] | None = None,
        backoff_initial: float = 1.0,
        backoff_max: float = 60.0,
        backoff_multiplier: float = 2.0,
        max_consecutive_failures: int | None = 5,
    ) -> None:
        """
        Args:
            url: base WS URL (default — prod /v1). Без query params — они
                собираются из topics/device_type/home_ids/external_device_ids.
            topics: список topic'ов на которые подписываемся при connect
                (Sber серилизованный формат: query param `topic` повторяется).
            device_type: query param `device_type` (UNKNOWN/BOX/PORTAL).
                Для интеграций, не являющихся официальным Sber-устройством, —
                UNKNOWN.
            home_ids: optional фильтр по конкретным homes (`desired_home_id`).
                None = все homes пользователя.
            external_device_ids: optional фильтр по device_id (`ext_dvc_id`).
                None = все устройства.
            max_consecutive_failures: после N подряд неудачных connect-попыток
                run() завершается (degraded mode). Полезно когда WS-endpoint
                отдаёт стабильный 4xx (неверный path) — лучше отказаться от WS
                и работать на polling, чем спамить логи. None = бесконечно.
                Сбрасывается при любом успешном recv-loop.
        """
        self._auth = auth
        self._callback = callback
        self._factory = factory
        self._base_url = url
        self._topics = tuple(topics)
        self._device_type = device_type
        self._home_ids = tuple(home_ids) if home_ids is not None else ()
        self._external_device_ids = (
            tuple(external_device_ids) if external_device_ids is not None else ()
        )
        self._backoff_initial = backoff_initial
        self._backoff_max = backoff_max
        self._backoff_multiplier = backoff_multiplier
        self._max_consecutive_failures = max_consecutive_failures

        self._stop_event = asyncio.Event()
        self._connection: WebSocketProtocol | None = None
        self._connected_event = asyncio.Event()

    @property
    def _url(self) -> str:
        """Полный URL с query string подписки (Sber serialized format)."""
        params: list[tuple[str, str]] = []
        for topic in self._topics:
            params.append(("topic", topic))
        # device_type — повторяемый, пока используем один
        params.append(("device_type", self._device_type))
        for home_id in self._home_ids:
            params.append(("desired_home_id", home_id))
        for ext_id in self._external_device_ids:
            params.append(("ext_dvc_id", ext_id))
        if not params:
            return self._base_url
        sep = "&" if "?" in self._base_url else "?"
        return f"{self._base_url}{sep}{urlencode(params)}"

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
        После `max_consecutive_failures` подряд connect-fails — graceful exit
        в degraded mode (log WARN, return).
        """
        backoff = self._backoff_initial
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                await self._connect_and_receive()
                # Успешный recv-loop — сбросим счётчик, новый connect без backoff
                consecutive_failures = 0
                backoff = self._backoff_initial
            except AuthError:
                # Critical: refresh не помог. Останавливаемся, callback должен решить дальше.
                _LOGGER.error("WebSocket auth failed, stopping")
                raise
            except SberError as err:
                consecutive_failures += 1
                _LOGGER.warning(
                    "WebSocket error (failure %d/%s): %s; reconnect in %.1fs",
                    consecutive_failures,
                    self._max_consecutive_failures or "∞",
                    err,
                    backoff,
                )
            except asyncio.CancelledError:
                _LOGGER.debug("WebSocket cancelled")
                raise
            except ConnectionResetError as err:
                # Обычное закрытие соединения сервером (Sber WS имеет TTL,
                # periodically reconnect даже при нормальной работе). Не
                # считаем это failure'ом, логируем debug вместо ERROR.
                _LOGGER.debug("WebSocket closed by peer (%s); reconnect in %.1fs", err, backoff)
            except Exception:
                consecutive_failures += 1
                _LOGGER.exception("Unexpected WebSocket error; reconnect in %.1fs", backoff)

            self._connected_event.clear()

            if (
                self._max_consecutive_failures is not None
                and consecutive_failures >= self._max_consecutive_failures
            ):
                _LOGGER.warning(
                    "WebSocket disabled after %d consecutive failures — "
                    "degrading to polling-only mode. Restart integration to retry.",
                    consecutive_failures,
                )
                return

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

        Sber API-format:
        - URL: `wss://<host>/v1?topic=...&device_type=...`
        - Header: `Authorization: Bearer <companion_jwt>`
        - Подписки на topic'и идут через query params при handshake,
          отдельного subscribe-сообщения нет.
        """
        token = await self._auth.access_token()
        url = self._url
        headers = {"Authorization": f"Bearer {token}"}
        try:
            conn = await self._factory(url, headers)
        except Exception as err:
            raise NetworkError(f"WS connect failed: {err}") from err

        self._connection = conn
        self._connected_event.set()
        _LOGGER.debug("WebSocket connected to %s", url)
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
