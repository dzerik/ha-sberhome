#!/usr/bin/env python3
"""CLI пример: подписаться на real-time DEVICE_STATE через WebSocket.

Печатает каждое входящее изменение состояния. Прерывается Ctrl+C.

Использование:

    python examples/ws_listen.py <companion_token>
"""

from __future__ import annotations

import asyncio
import sys

import httpx

from aiosber import SocketMessageDto, Topic, TopicRouter, WebSocketClient
from aiosber.auth import AuthManager, CompanionTokens, InMemoryTokenStore


async def on_device_state(msg: SocketMessageDto) -> None:
    state = msg.state
    if state is None:
        return
    print(f"\n[{state.timestamp}] DEVICE_STATE:")
    for attr in state.reported_state:
        print(f"  {attr.key:<25} = {attr.value}")


async def on_devman_event(msg: SocketMessageDto) -> None:
    print(f"\n[event] DEVMAN: {msg.event}")


async def main(token: str) -> int:
    http = httpx.AsyncClient()
    store = InMemoryTokenStore(initial=CompanionTokens(access_token=token, expires_in=3600))
    auth = AuthManager(http=http, store=store)

    router = TopicRouter()
    router.on(Topic.DEVICE_STATE, on_device_state)
    router.on(Topic.DEVMAN_EVENT, on_devman_event)

    ws = WebSocketClient(auth=auth, callback=router)
    print("Connecting to wss://ws.iot.sberdevices.ru ...")
    print("Ctrl+C to stop\n")
    try:
        await ws.run()
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        await ws.stop()
        await http.aclose()
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(asyncio.run(main(sys.argv[1])))
    except KeyboardInterrupt:
        sys.exit(0)
