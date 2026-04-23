"""Транспортный слой aiosber: HTTP, WebSocket, SSL.

- `ssl.SslContextProvider` — async-friendly SSL context с Russian Trusted Root CA.
- `http.HttpTransport` — httpx-обёртка с retry, headers, error mapping.
- `ws.WebSocketClient` — WebSocket с reconnect и dispatcher (PR #3).
"""

from __future__ import annotations

from .http import HttpTransport
from .ssl import SslContextProvider
from .ws import (
    MessageCallback,
    TopicRouter,
    WebSocketClient,
    WebSocketFactory,
    WebSocketProtocol,
    default_websockets_factory,
)

__all__ = [
    "HttpTransport",
    "MessageCallback",
    "SslContextProvider",
    "TopicRouter",
    "WebSocketClient",
    "WebSocketFactory",
    "WebSocketProtocol",
    "default_websockets_factory",
]
