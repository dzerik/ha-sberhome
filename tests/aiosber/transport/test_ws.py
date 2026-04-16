"""Тесты WebSocketClient — connect, dispatch, reconnect, auth."""

from __future__ import annotations

import asyncio
import contextlib
import json

import httpx
import pytest

from custom_components.sberhome.aiosber import (
    SocketMessageDto,
    Topic,
    TopicRouter,
    WebSocketClient,
)
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)


# ---------------------------------------------------------------------------
# In-memory mock WebSocket
# ---------------------------------------------------------------------------
class FakeWebSocket:
    """In-memory WebSocketProtocol для тестов.

    Сценарий: предзаполненная очередь incoming messages + опциональное
    закрытие через close_after_messages.
    """

    def __init__(
        self,
        messages: list[str],
        *,
        close_after_messages: bool = True,
        raise_on_recv: Exception | None = None,
    ) -> None:
        self._messages = list(messages)
        self._close_after = close_after_messages
        self._raise_on_recv = raise_on_recv
        self.sent: list[str | bytes] = []
        self.closed = False
        self._close_event = asyncio.Event()

    async def recv(self) -> str:
        if self._raise_on_recv is not None:
            raise self._raise_on_recv
        if self._messages:
            return self._messages.pop(0)
        if self._close_after:
            # Имитируем чистое закрытие сервером — обычная сетевая ошибка,
            # WebSocketClient должен попытаться reconnect.
            raise ConnectionResetError("server closed connection")
        # Block forever (until close())
        await self._close_event.wait()
        raise ConnectionResetError("closed")

    async def send(self, data: str | bytes) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self.closed = True
        self._close_event.set()


def _build_auth(token: str = "TOK") -> AuthManager:
    """Build AuthManager with stub HttpClient + initial token."""
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token=token, expires_in=3600))
    return AuthManager(http=http, store=store)


def _msg_device_state() -> str:
    return json.dumps({
        "state": {
            "reported_state": [{"key": "on_off", "type": "BOOL", "bool_value": True}],
            "timestamp": "2026-04-16T12:00:00.000Z",
        }
    })


def _msg_devman_event() -> str:
    return json.dumps({"event": {"device_id": "x", "type": "button_1_event"}})


# ---------------------------------------------------------------------------
# Basic dispatch
# ---------------------------------------------------------------------------
async def test_basic_dispatch_one_message():
    received: list[SocketMessageDto] = []
    fake = FakeWebSocket([_msg_device_state()])

    async def factory(url: str, headers: dict[str, str]):
        return fake

    client = WebSocketClient(
        auth=_build_auth(),
        callback=lambda m: received.append(m),
        factory=factory,
        backoff_initial=0.01,
    )

    task = asyncio.create_task(client.run())
    # Подождать обработки сообщения, потом stop
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.01)
    await client.stop()
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except (TimeoutError, asyncio.CancelledError):
        task.cancel()

    assert len(received) == 1
    assert received[0].topic is Topic.DEVICE_STATE


async def test_factory_called_with_bearer_header():
    """WS handshake идёт с Authorization: Bearer <companion_jwt>."""
    captured: dict = {}
    fake = FakeWebSocket([])  # сразу закрывается

    async def factory(url: str, headers: dict[str, str]):
        captured["url"] = url
        captured["headers"] = headers
        return fake

    client = WebSocketClient(
        auth=_build_auth(token="MYTOK"),
        callback=lambda m: None,
        factory=factory,
        backoff_initial=0.01,
    )
    task = asyncio.create_task(client.run())
    await asyncio.sleep(0.05)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert "headers" in captured
    assert captured["headers"]["Authorization"] == "Bearer MYTOK"


async def test_url_has_topic_and_device_type_query_params():
    """Подписка на topic'и и device_type — через query string при handshake."""
    captured: dict = {}
    fake = FakeWebSocket([])

    async def factory(url: str, headers: dict[str, str]):
        captured["url"] = url
        return fake

    client = WebSocketClient(
        auth=_build_auth(),
        callback=lambda m: None,
        factory=factory,
        topics=("DEVICE_STATE", "DEVMAN_EVENT"),
        device_type="UNKNOWN",
        backoff_initial=0.01,
    )
    task = asyncio.create_task(client.run())
    await asyncio.sleep(0.05)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    url = captured["url"]
    assert "topic=DEVICE_STATE" in url
    assert "topic=DEVMAN_EVENT" in url
    assert "device_type=UNKNOWN" in url


async def test_url_appends_optional_filters():
    """home_ids и external_device_ids — опциональные query params."""
    captured: dict = {}
    fake = FakeWebSocket([])

    async def factory(url: str, headers: dict[str, str]):
        captured["url"] = url
        return fake

    client = WebSocketClient(
        auth=_build_auth(),
        callback=lambda m: None,
        factory=factory,
        topics=("DEVICE_STATE",),
        home_ids=("home-A", "home-B"),
        external_device_ids=("dev-1",),
        backoff_initial=0.01,
    )
    task = asyncio.create_task(client.run())
    await asyncio.sleep(0.05)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    url = captured["url"]
    assert "desired_home_id=home-A" in url
    assert "desired_home_id=home-B" in url
    assert "ext_dvc_id=dev-1" in url


async def test_async_callback_supported():
    received: list[SocketMessageDto] = []

    async def callback(msg: SocketMessageDto) -> None:
        received.append(msg)

    fake = FakeWebSocket([_msg_device_state(), _msg_devman_event()])

    async def factory(url, headers):
        return fake

    client = WebSocketClient(auth=_build_auth(), callback=callback, factory=factory)
    task = asyncio.create_task(client.run())
    for _ in range(50):
        if len(received) >= 2:
            break
        await asyncio.sleep(0.01)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert len(received) == 2
    topics = sorted(m.topic.value for m in received if m.topic)
    assert topics == [Topic.DEVICE_STATE.value, Topic.DEVMAN_EVENT.value]


# ---------------------------------------------------------------------------
# Bad messages — non-JSON, non-object
# ---------------------------------------------------------------------------
async def test_invalid_json_ignored():
    received = []
    fake = FakeWebSocket(["not json at all", _msg_device_state()])

    async def factory(url, headers):
        return fake

    client = WebSocketClient(
        auth=_build_auth(), callback=lambda m: received.append(m), factory=factory
    )
    task = asyncio.create_task(client.run())
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.01)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert len(received) == 1


async def test_bytes_message_decoded():
    received = []
    raw_bytes = _msg_device_state().encode("utf-8")
    fake = FakeWebSocket([raw_bytes])  # type: ignore[list-item]

    async def factory(url, headers):
        return fake

    client = WebSocketClient(
        auth=_build_auth(), callback=lambda m: received.append(m), factory=factory
    )
    task = asyncio.create_task(client.run())
    for _ in range(50):
        if received:
            break
        await asyncio.sleep(0.01)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert len(received) == 1
    assert received[0].topic is Topic.DEVICE_STATE


# ---------------------------------------------------------------------------
# Callback exceptions don't break loop
# ---------------------------------------------------------------------------
async def test_callback_exception_isolated():
    """Если callback бросает — WS loop продолжает работать."""
    received = []

    def callback(msg):
        received.append(msg)
        if len(received) == 1:
            raise RuntimeError("callback boom")

    fake = FakeWebSocket([_msg_device_state(), _msg_device_state()])

    async def factory(url, headers):
        return fake

    client = WebSocketClient(auth=_build_auth(), callback=callback, factory=factory)
    task = asyncio.create_task(client.run())
    for _ in range(50):
        if len(received) >= 2:
            break
        await asyncio.sleep(0.01)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert len(received) == 2  # обе обработаны


# ---------------------------------------------------------------------------
# Reconnect
# ---------------------------------------------------------------------------
async def test_reconnect_after_disconnect():
    """После закрытия первого соединения — переподключение."""
    factory_calls = 0
    received = []

    async def factory(url, headers):
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls == 1:
            # Первое соединение даёт одно сообщение и закрывается
            return FakeWebSocket([_msg_device_state()])
        # Второе — снова одно
        return FakeWebSocket([_msg_devman_event()])

    client = WebSocketClient(
        auth=_build_auth(),
        callback=lambda m: received.append(m),
        factory=factory,
        backoff_initial=0.01,
        backoff_max=0.05,
    )
    task = asyncio.create_task(client.run())
    for _ in range(100):
        if len(received) >= 2:
            break
        await asyncio.sleep(0.01)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert factory_calls >= 2
    assert len(received) >= 2


async def test_reconnect_with_backoff_on_factory_error():
    """Если factory бросает — reconnect с backoff (но не падаем)."""
    factory_calls = 0

    async def factory(url, headers):
        nonlocal factory_calls
        factory_calls += 1
        if factory_calls < 3:
            raise ConnectionError("transient network failure")
        # Третий вызов — успешный, но с пустой очередью (быстро закрывается)
        return FakeWebSocket([])

    client = WebSocketClient(
        auth=_build_auth(),
        callback=lambda m: None,
        factory=factory,
        backoff_initial=0.01,
        backoff_max=0.05,
    )
    task = asyncio.create_task(client.run())
    for _ in range(100):
        if factory_calls >= 3:
            break
        await asyncio.sleep(0.01)
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task

    assert factory_calls >= 3


# ---------------------------------------------------------------------------
# stop()
# ---------------------------------------------------------------------------
async def test_stop_terminates_loop():
    fake = FakeWebSocket([], close_after_messages=False)

    async def factory(url, headers):
        return fake

    client = WebSocketClient(
        auth=_build_auth(), callback=lambda m: None, factory=factory
    )
    task = asyncio.create_task(client.run())
    await client.wait_until_connected(timeout=1.0)
    await client.stop()

    with contextlib.suppress(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=1.0)
    assert fake.closed


async def test_is_connected_property():
    fake = FakeWebSocket([], close_after_messages=False)

    async def factory(url, headers):
        return fake

    client = WebSocketClient(
        auth=_build_auth(), callback=lambda m: None, factory=factory
    )
    assert not client.is_connected
    task = asyncio.create_task(client.run())
    await client.wait_until_connected(timeout=1.0)
    assert client.is_connected
    await client.stop()
    task.cancel()
    with contextlib.suppress(BaseException):
        await task


# ---------------------------------------------------------------------------
# TopicRouter
# ---------------------------------------------------------------------------
async def test_topic_router_dispatches_by_topic():
    state_msgs = []
    event_msgs = []

    router = TopicRouter()
    router.on(Topic.DEVICE_STATE, lambda m: state_msgs.append(m))
    router.on(Topic.DEVMAN_EVENT, lambda m: event_msgs.append(m))

    state = SocketMessageDto.from_dict(json.loads(_msg_device_state()))
    event = SocketMessageDto.from_dict(json.loads(_msg_devman_event()))
    assert state is not None and event is not None

    await router(state)
    await router(event)

    assert len(state_msgs) == 1
    assert len(event_msgs) == 1


async def test_topic_router_ignores_unsubscribed_topics():
    received = []
    router = TopicRouter()
    router.on(Topic.DEVICE_STATE, lambda m: received.append(m))

    # Сообщение с другим топиком
    event = SocketMessageDto.from_dict(json.loads(_msg_devman_event()))
    await router(event)

    assert received == []


async def test_topic_router_supports_multiple_handlers_per_topic():
    a = []
    b = []
    router = TopicRouter()
    router.on(Topic.DEVICE_STATE, lambda m: a.append(m))
    router.on(Topic.DEVICE_STATE, lambda m: b.append(m))

    state = SocketMessageDto.from_dict(json.loads(_msg_device_state()))
    await router(state)

    assert len(a) == 1 and len(b) == 1


async def test_topic_router_async_handler_supported():
    received = []

    async def handler(msg):
        received.append(msg)

    router = TopicRouter()
    router.on(Topic.DEVICE_STATE, handler)

    state = SocketMessageDto.from_dict(json.loads(_msg_device_state()))
    await router(state)

    assert len(received) == 1


# ---------------------------------------------------------------------------
# default_websockets_factory ImportError if lib missing
# ---------------------------------------------------------------------------
async def test_default_factory_helpful_error_when_websockets_missing():
    """Если websockets не установлен — понятная ошибка."""
    from custom_components.sberhome.aiosber.exceptions import SberError
    from custom_components.sberhome.aiosber.transport import default_websockets_factory

    # Попробуем — если websockets установлен, тест пропустим
    try:
        import websockets  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        with pytest.raises(SberError, match="websockets library required"):
            await default_websockets_factory("wss://example/", {})
