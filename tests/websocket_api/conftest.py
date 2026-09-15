"""Фикстуры для команд панели через настоящий WebSocket Home Assistant."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.core import HomeAssistant


class Panel:
    """Клиент панели: команды ``sberhome/<command>`` от имени администратора.

    События подписок, пришедшие раньше ответа на команду, не теряются —
    они копятся и читаются через :meth:`event`.
    """

    def __init__(self, client: Any) -> None:
        self.client = client
        self._last_id = 0
        self._events: list[dict[str, Any]] = []

    async def __call__(self, command: str, **fields: Any) -> dict[str, Any]:
        """Отправить ``sberhome/<command>`` и вернуть ответ целиком."""
        return await self.raw({"type": f"sberhome/{command}", **fields})

    async def raw(self, message: dict[str, Any]) -> dict[str, Any]:
        """Отправить произвольную команду WebSocket API и дождаться её ответа."""
        self._last_id += 1
        msg_id = self._last_id
        await self.client.send_json({"id": msg_id, **message})
        while True:
            response = await self.client.receive_json()
            if response["type"] == "result" and response["id"] == msg_id:
                return response
            self._events.append(response)

    async def event(self, subscription: int) -> dict[str, Any]:
        """Следующее событие подписки ``subscription`` (поле ``event``)."""
        for index, message in enumerate(self._events):
            if message["id"] == subscription:
                return self._events.pop(index)["event"]
        while True:
            message = await self.client.receive_json()
            if message["id"] == subscription and message["type"] == "event":
                return message["event"]
            self._events.append(message)

    def pending_events(self, subscription: int) -> list[dict[str, Any]]:
        """События подписки, уже полученные, но ещё не прочитанные."""
        return [m["event"] for m in self._events if m["id"] == subscription]


@pytest.fixture
async def panel(hass: HomeAssistant, hass_ws_client: Any) -> Panel:
    """Панель SberHome, подключённая к Home Assistant по WebSocket."""
    return Panel(await hass_ws_client(hass))
