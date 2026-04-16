"""Тесты InMemoryTokenStore."""

from __future__ import annotations

from custom_components.sberhome.aiosber.auth import (
    CompanionTokens,
    InMemoryTokenStore,
)


async def test_empty_store_returns_none():
    store = InMemoryTokenStore()
    assert await store.load() is None


async def test_save_then_load():
    store = InMemoryTokenStore()
    tokens = CompanionTokens(access_token="X", expires_in=3600)
    await store.save(tokens)
    loaded = await store.load()
    assert loaded is tokens


async def test_save_overwrites():
    store = InMemoryTokenStore()
    await store.save(CompanionTokens(access_token="A"))
    await store.save(CompanionTokens(access_token="B"))
    loaded = await store.load()
    assert loaded is not None
    assert loaded.access_token == "B"


async def test_clear():
    store = InMemoryTokenStore()
    await store.save(CompanionTokens(access_token="X"))
    await store.clear()
    assert await store.load() is None


async def test_clear_idempotent():
    store = InMemoryTokenStore()
    await store.clear()
    await store.clear()  # не должно бросить


async def test_initial_token():
    initial = CompanionTokens(access_token="preset")
    store = InMemoryTokenStore(initial=initial)
    assert (await store.load()) is initial
