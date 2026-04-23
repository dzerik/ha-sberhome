"""HA-side WebSocket adapter — aiohttp реализация `WebSocketProtocol` из aiosber.

Зачем отдельный adapter:
- `aiosber.transport.ws` определяет `WebSocketProtocol` (`recv` / `send` / `close`).
- `aiosber.transport.ws.default_websockets_factory` использует библиотеку `websockets`.
- HA core всё равно тянет `aiohttp` → переиспользуем его (одна меньше зависимость).
- `aiosber/` НЕ может импортировать `aiohttp` (CLAUDE.md: zero HA imports).
  Поэтому adapter живёт в HA-side как `_ws_adapter.py`.

Использование:

    session = async_get_clientsession(hass)
    factory = make_aiohttp_factory(session)
    ws = WebSocketClient(auth=auth, callback=router, factory=factory)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import aiohttp


class AiohttpWsAdapter:
    """Wrapper над `aiohttp.ClientWebSocketResponse` под `WebSocketProtocol`.

    `recv()` блокирует пока не пришло сообщение. На close/error поднимает
    `ConnectionResetError` — `WebSocketClient` обработает его как сетевую ошибку
    и попытается reconnect.
    """

    __slots__ = ("_ws",)

    def __init__(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._ws = ws

    async def recv(self) -> str | bytes:
        msg = await self._ws.receive()
        if msg.type == aiohttp.WSMsgType.TEXT:
            return msg.data
        if msg.type == aiohttp.WSMsgType.BINARY:
            return msg.data
        # CLOSE / CLOSING / CLOSED / ERROR
        raise ConnectionResetError(f"WS closed with type={msg.type.name}")

    async def send(self, data: str | bytes) -> None:
        if isinstance(data, bytes):
            await self._ws.send_bytes(data)
        else:
            await self._ws.send_str(data)

    async def close(self) -> None:
        if not self._ws.closed:
            await self._ws.close()


def make_aiohttp_factory(session: aiohttp.ClientSession) -> Callable[..., Any]:
    """Создать `WebSocketFactory`-совместимую функцию на основе aiohttp session.

    Args:
        session: shared `aiohttp.ClientSession` (получи через
            `homeassistant.helpers.aiohttp_client.async_get_clientsession`).

    Returns:
        Async factory `(url, headers) -> AiohttpWsAdapter`. Передавай в
        `WebSocketClient(factory=...)`.
    """

    async def factory(url: str, headers: dict[str, str]) -> AiohttpWsAdapter:
        ws = await session.ws_connect(url, headers=headers)
        return AiohttpWsAdapter(ws)

    return factory
