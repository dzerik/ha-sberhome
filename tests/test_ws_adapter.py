"""Tests для _ws_adapter — aiohttp wrapper над WebSocketProtocol."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.sberhome._ws_adapter import (
    AiohttpWsAdapter,
    make_aiohttp_factory,
)


def _make_msg(typ: aiohttp.WSMsgType, data) -> MagicMock:
    msg = MagicMock()
    msg.type = typ
    msg.data = data
    return msg


# ============== AiohttpWsAdapter ==============
class TestAiohttpWsAdapter:
    @pytest.mark.asyncio
    async def test_recv_text(self):
        ws = MagicMock()
        ws.receive = AsyncMock(return_value=_make_msg(aiohttp.WSMsgType.TEXT, "hello"))
        adapter = AiohttpWsAdapter(ws)
        assert await adapter.recv() == "hello"

    @pytest.mark.asyncio
    async def test_recv_binary(self):
        ws = MagicMock()
        ws.receive = AsyncMock(return_value=_make_msg(aiohttp.WSMsgType.BINARY, b"\x00\x01"))
        adapter = AiohttpWsAdapter(ws)
        assert await adapter.recv() == b"\x00\x01"

    @pytest.mark.asyncio
    async def test_recv_close_raises_connection_reset(self):
        ws = MagicMock()
        ws.receive = AsyncMock(return_value=_make_msg(aiohttp.WSMsgType.CLOSE, None))
        adapter = AiohttpWsAdapter(ws)
        with pytest.raises(ConnectionResetError):
            await adapter.recv()

    @pytest.mark.asyncio
    async def test_recv_error_raises(self):
        ws = MagicMock()
        ws.receive = AsyncMock(return_value=_make_msg(aiohttp.WSMsgType.ERROR, None))
        adapter = AiohttpWsAdapter(ws)
        with pytest.raises(ConnectionResetError):
            await adapter.recv()

    @pytest.mark.asyncio
    async def test_send_str(self):
        ws = MagicMock()
        ws.send_str = AsyncMock()
        ws.send_bytes = AsyncMock()
        adapter = AiohttpWsAdapter(ws)
        await adapter.send("data")
        ws.send_str.assert_called_once_with("data")
        ws.send_bytes.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_bytes(self):
        ws = MagicMock()
        ws.send_str = AsyncMock()
        ws.send_bytes = AsyncMock()
        adapter = AiohttpWsAdapter(ws)
        await adapter.send(b"data")
        ws.send_bytes.assert_called_once_with(b"data")
        ws.send_str.assert_not_called()

    @pytest.mark.asyncio
    async def test_close_calls_aiohttp_close(self):
        ws = MagicMock()
        ws.closed = False
        ws.close = AsyncMock()
        adapter = AiohttpWsAdapter(ws)
        await adapter.close()
        ws.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_idempotent_when_already_closed(self):
        ws = MagicMock()
        ws.closed = True
        ws.close = AsyncMock()
        adapter = AiohttpWsAdapter(ws)
        await adapter.close()
        ws.close.assert_not_called()


# ============== make_aiohttp_factory ==============
class TestMakeAiohttpFactory:
    @pytest.mark.asyncio
    async def test_factory_returns_adapter(self):
        session = MagicMock()
        ws_response = MagicMock()
        session.ws_connect = AsyncMock(return_value=ws_response)

        factory = make_aiohttp_factory(session)
        adapter = await factory("wss://example/", {"Authorization": "Bearer X"})

        assert isinstance(adapter, AiohttpWsAdapter)
        session.ws_connect.assert_called_once_with(
            "wss://example/",
            headers={"Authorization": "Bearer X"},
        )
