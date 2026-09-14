"""Права доступа к WebSocket API панели SberHome.

Все команды панели — административные: они меняют выбор устройств и
комнаты, отправляют сырые сообщения в обработчики, выдают временный
пароль Wi-Fi для сопряжения и весь журнал обмена с облаком. До 5.38.1
ни одна из них не требовала прав администратора, и любой пользователь
Home Assistant мог их вызвать.

Проверка идёт по реально зарегистрированным обработчикам, а не по
декораторам в исходниках: новая команда, добавленная в ``_COMMANDS`` без
защиты или зарегистрированная в обход неё, роняет тест.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import Unauthorized

import custom_components.sberhome.websocket_api as ws_pkg
from custom_components.sberhome import _async_register_panel
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.websocket_api import async_setup_websocket_api

WS_REGISTRY_KEY = "websocket_api"
"""Ключ ``hass.data``, под которым HA хранит зарегистрированные команды."""

PREFIX = f"{DOMAIN}/"


def _make_hass() -> tuple[MagicMock, list[str]]:
    """Заглушка hass, достаточная для регистрации и вызова команд."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.config_entries.async_loaded_entries = MagicMock(return_value=[])
    scheduled: list[str] = []

    def _schedule(coro: Any, name: str | None = None, **_kwargs: Any) -> None:
        scheduled.append(name or "task")
        coro.close()

    hass.async_create_background_task = _schedule
    hass.async_create_task = _schedule
    return hass, scheduled


def _make_connection(*, is_admin: bool) -> MagicMock:
    conn = MagicMock()
    conn.user = MagicMock()
    conn.user.is_admin = is_admin
    conn.subscriptions = {}
    return conn


def _registered_handlers(hass: MagicMock) -> dict[str, Any]:
    async_setup_websocket_api(hass)
    handlers = hass.data[WS_REGISTRY_KEY]
    return {cmd: handler for cmd, (handler, _schema) in handlers.items() if cmd.startswith(PREFIX)}


class TestAdminGate:
    """Каждая команда панели доступна только администратору."""

    def test_registered_set_matches_commands_tuple(self) -> None:
        hass, _ = _make_hass()
        registered = set(_registered_handlers(hass))
        assert registered == {command._ws_command for command in ws_pkg._COMMANDS}
        assert "sberhome/pairing/wifi_credentials" in registered

    def test_every_command_rejects_non_admin(self) -> None:
        hass, scheduled = _make_hass()
        unprotected: list[str] = []
        for cmd, handler in _registered_handlers(hass).items():
            conn = _make_connection(is_admin=False)
            try:
                handler(hass, conn, {"id": 1, "type": cmd})
            except Unauthorized:
                pass
            else:
                unprotected.append(cmd)
                continue
            assert not conn.send_result.called, f"{cmd}: обработчик выполнился"
            assert not conn.send_error.called, f"{cmd}: обработчик выполнился"
            assert not conn.send_message.called, f"{cmd}: обработчик выполнился"
        assert not unprotected, f"команды доступны не-администратору: {unprotected}"
        assert not scheduled, f"для не-администратора запланированы задачи: {scheduled}"

    def test_every_command_rejects_missing_user(self) -> None:
        hass, _ = _make_hass()
        for cmd, handler in _registered_handlers(hass).items():
            conn = _make_connection(is_admin=True)
            conn.user = None
            with pytest.raises(Unauthorized):
                handler(hass, conn, {"id": 1, "type": cmd})

    def test_every_command_admits_admin(self) -> None:
        """Администратор проходит: обработчик отвечает или планирует задачу."""
        hass, scheduled = _make_hass()
        broken: list[str] = []
        for cmd, handler in _registered_handlers(hass).items():
            conn = _make_connection(is_admin=True)
            before = len(scheduled)
            try:
                handler(hass, conn, {"id": 1, "type": cmd})
            except Unauthorized:
                broken.append(f"{cmd}: администратор отклонён")
                continue
            except Exception:  # noqa: BLE001 — тело выполнилось, дальше заглушки не хватило
                continue
            if not (conn.send_result.called or conn.send_error.called or len(scheduled) > before):
                broken.append(f"{cmd}: обработчик не выполнился")
        assert not broken, broken


@pytest.mark.asyncio
async def test_panel_requires_admin() -> None:
    hass = MagicMock()
    hass.data = {}
    hass.http.async_register_static_paths = AsyncMock()
    integration = MagicMock()
    integration.version = "5.38.1"

    with (
        patch(
            "custom_components.sberhome.async_get_integration", AsyncMock(return_value=integration)
        ),
        patch("custom_components.sberhome.async_register_built_in_panel") as mock_register,
    ):
        await _async_register_panel(hass)

    assert mock_register.call_args.kwargs["require_admin"] is True
