"""Tests for the SberHome auth state module — PendingFlow + TTL/GC."""

from __future__ import annotations

from time import monotonic
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.auth_state import (
    PendingFlow,
    cleanup_expired,
    pending_auth_flows,
)


@pytest.fixture(autouse=True)
def _cleanup_auth_flows():
    """Очистить глобальный pending_auth_flows перед/после каждого теста —
    иначе порядок тестов влияет на результат (module-level dict)."""
    pending_auth_flows.clear()
    yield
    pending_auth_flows.clear()


def test_pending_auth_flows_is_dict():
    assert isinstance(pending_auth_flows, dict)


def test_pending_flow_stores_client_and_timestamp():
    mock_client = MagicMock()
    flow = PendingFlow(client=mock_client)
    assert flow.client is mock_client
    assert flow.created_at > 0  # monotonic fills default


@pytest.mark.asyncio
async def test_cleanup_expired_removes_old_flows_and_closes_clients():
    """Flow старше TTL должен быть удалён + client.aclose() вызван.

    Без этого brought-up-but-not-finished OAuth flow (пользователь
    закрыл вкладку) оставляет httpx.AsyncClient в памяти до рестарта HA.
    """
    old_client = MagicMock()
    old_client.aclose = AsyncMock()
    fresh_client = MagicMock()
    fresh_client.aclose = AsyncMock()

    # Старый flow — created_at в прошлом (30 минут назад)
    pending_auth_flows["old"] = PendingFlow(client=old_client, created_at=monotonic() - 1800)
    # Свежий
    pending_auth_flows["fresh"] = PendingFlow(client=fresh_client)

    removed = await cleanup_expired(ttl=600)  # 10 минут

    assert removed == ["old"]
    assert "old" not in pending_auth_flows
    assert "fresh" in pending_auth_flows
    old_client.aclose.assert_awaited_once()
    fresh_client.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_expired_keeps_all_fresh_flows():
    """Если все flows свежие — ничего не удаляется."""
    mock_client = MagicMock()
    mock_client.aclose = AsyncMock()
    pending_auth_flows["fresh"] = PendingFlow(client=mock_client)

    removed = await cleanup_expired(ttl=600)

    assert removed == []
    assert "fresh" in pending_auth_flows
    mock_client.aclose.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_expired_swallows_aclose_errors():
    """Если `aclose()` падает (например httpx уже закрыт другим путём),
    cleanup продолжается для остальных flows. Best-effort — мы не хотим
    чтобы одна ошибка мешала чистке другого ресурса."""
    failing_client = MagicMock()
    failing_client.aclose = AsyncMock(side_effect=RuntimeError("already closed"))
    good_client = MagicMock()
    good_client.aclose = AsyncMock()

    pending_auth_flows["bad"] = PendingFlow(client=failing_client, created_at=monotonic() - 1800)
    pending_auth_flows["good"] = PendingFlow(client=good_client, created_at=monotonic() - 1800)

    removed = await cleanup_expired(ttl=600)

    # Оба удалены из dict несмотря на aclose error
    assert set(removed) == {"bad", "good"}
    assert pending_auth_flows == {}
    failing_client.aclose.assert_awaited_once()
    good_client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_expired_on_empty_dict_is_noop():
    """Пустой dict — cleanup не падает."""
    removed = await cleanup_expired()
    assert removed == []
