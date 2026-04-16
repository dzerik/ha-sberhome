"""Async SSL context provider for sberdevices.ru endpoints.

`ssl.create_default_context()` — синхронная операция (читает trust store,
парсит CA-bundle), которая может занимать ~50-200 мс. Блокировать event loop
нельзя, поэтому первая инициализация делается через `loop.run_in_executor`.

Принципы:
- НЕТ global state — каждый инстанс хранит свой кеш.
- НЕТ tempfile — CA загружается через `cadata=` (in-memory), не через путь.
- Первый вызов `get()` блокирующий (executor); последующие — мгновенные.

Использование:

    ssl_provider = SslContextProvider()
    ctx = await ssl_provider.get()
    transport = httpx.AsyncHTTPTransport(verify=ctx)
"""

from __future__ import annotations

import asyncio
import ssl
from typing import Final

from ..const import ROOT_CA_PEM


class SslContextProvider:
    """Lazy async builder of `ssl.SSLContext` with Russian Trusted Root CA.

    Args:
        ca_pem: PEM-encoded CA cert(s) to trust. По умолчанию —
            `ROOT_CA_PEM` (Russian Trusted Root CA от Минцифры).

    Thread/async safety: один `get()` за раз; повторные конкурентные вызовы
    дожидаются первого через asyncio.Lock.
    """

    __slots__ = ("_ca_pem", "_context", "_lock")

    def __init__(self, ca_pem: str = ROOT_CA_PEM) -> None:
        self._ca_pem: Final = ca_pem
        self._context: ssl.SSLContext | None = None
        self._lock = asyncio.Lock()

    async def get(self) -> ssl.SSLContext:
        """Return cached SSL context, creating it on first call (in executor)."""
        if self._context is not None:
            return self._context
        async with self._lock:
            if self._context is None:  # double-checked locking
                loop = asyncio.get_running_loop()
                self._context = await loop.run_in_executor(None, self._build)
        return self._context

    def _build(self) -> ssl.SSLContext:
        """Synchronous builder. Run в executor."""
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cadata=self._ca_pem)
        return ctx

    def reset(self) -> None:
        """Сбросить кеш (для тестов или принудительной пересборки)."""
        self._context = None
