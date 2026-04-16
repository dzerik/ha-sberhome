"""Тесты SslContextProvider."""

from __future__ import annotations

import asyncio
import ssl

import pytest

from custom_components.sberhome.aiosber.transport import SslContextProvider


async def test_get_returns_ssl_context():
    p = SslContextProvider()
    ctx = await p.get()
    assert isinstance(ctx, ssl.SSLContext)


async def test_get_caches_context():
    p = SslContextProvider()
    ctx1 = await p.get()
    ctx2 = await p.get()
    assert ctx1 is ctx2


async def test_concurrent_calls_share_one_build():
    """5 одновременных get() — context создаётся только раз."""
    builds = 0

    class CountingProvider(SslContextProvider):
        def _build(self) -> ssl.SSLContext:
            nonlocal builds
            builds += 1
            return super()._build()

    p = CountingProvider()
    contexts = await asyncio.gather(*[p.get() for _ in range(5)])
    assert all(c is contexts[0] for c in contexts)
    assert builds == 1


async def test_reset_invalidates_cache():
    p = SslContextProvider()
    ctx1 = await p.get()
    p.reset()
    ctx2 = await p.get()
    assert ctx1 is not ctx2


async def test_no_global_state_between_instances():
    """Два разных SslContextProvider имеют разные контексты."""
    p1 = SslContextProvider()
    p2 = SslContextProvider()
    ctx1 = await p1.get()
    ctx2 = await p2.get()
    assert ctx1 is not ctx2


async def test_custom_ca_pem():
    """Можно подать свой CA. Невалидный PEM — должен бросить."""
    p = SslContextProvider(ca_pem="-----BEGIN CERTIFICATE-----\nINVALID\n-----END CERTIFICATE-----")
    with pytest.raises(ssl.SSLError):
        await p.get()
