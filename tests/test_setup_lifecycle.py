"""Жизненный цикл записи в настоящем Home Assistant: ничего не утекает.

Настройка создаёт httpx-клиент, WebSocket-задачу и данные записи в
``hass.data``. Прерванная настройка (облако недоступно, сломанные токены,
ошибка после первого опроса) и выгрузка записи должны освобождать всё это:
при недоступном облаке HA повторяет настройку бесконечно, и каждая попытка
иначе оставляла бы открытый пул соединений и мусор в ``hass.data``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome.aiosber.auth import AuthManager
from custom_components.sberhome.aiosber.const import AUTH_METHOD_CSAFRONT
from custom_components.sberhome.aiosber.transport import HttpTransport
from custom_components.sberhome.api import SberAPI
from custom_components.sberhome.const import CONF_AUTH_METHOD, CONF_TOKEN, DOMAIN
from custom_components.sberhome.coordinator import SberHomeCoordinator

_TOKEN = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "obtained_at": 0}


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Дать загрузчику HA найти ``custom_components/sberhome``.

    При editable-установке (как в CI) в ``custom_components.__path__`` попадает
    строка-заглушка, на которой загрузчик HA падает; оставляем только каталоги.
    """
    import custom_components

    real_dirs = [p for p in dict.fromkeys(custom_components.__path__) if Path(p).is_dir()]
    monkeypatch.setattr(custom_components, "__path__", real_dirs)


@pytest.fixture
def clients() -> Iterator[list[httpx.AsyncClient]]:
    """Все httpx-клиенты, созданные настройкой записи; сеть не используется."""
    created: list[httpx.AsyncClient] = []

    def _factory(*_args: Any, **_kwargs: Any) -> httpx.AsyncClient:
        client = httpx.AsyncClient()
        created.append(client)
        return client

    with (
        patch("custom_components.sberhome.httpx", SimpleNamespace(AsyncClient=_factory)),
        patch("custom_components.sberhome.async_init_ssl", AsyncMock(return_value=None)),
        # Панели нужен HTTP-сервер HA — к утечкам ресурсов записи она не относится.
        patch("custom_components.sberhome._async_register_panel", AsyncMock()),
    ):
        yield created


def _entry(hass: HomeAssistant, **kwargs: Any) -> MockConfigEntry:
    kwargs.setdefault("data", {CONF_TOKEN: dict(_TOKEN)})
    kwargs.setdefault("options", {"enabled_device_ids": []})
    entry = MockConfigEntry(domain=DOMAIN, version=2, title="SberHome", **kwargs)
    entry.add_to_hass(hass)
    return entry


def _entry_keys(hass: HomeAssistant, entry: MockConfigEntry) -> list[str]:
    return [key for key in hass.data if isinstance(key, str) and entry.entry_id in key]


def _open(clients: list[httpx.AsyncClient]) -> list[httpx.AsyncClient]:
    return [client for client in clients if not client.is_closed]


async def _never_ending_ws(self: SberHomeCoordinator) -> None:
    await asyncio.Event().wait()


_WS_TASKS: list[asyncio.Task] = []


async def _update_starting_ws(self: SberHomeCoordinator) -> dict[str, Any]:
    """Успешный опрос без облака, запускающий WebSocket, как настоящий."""
    if self._ws_task is None or self._ws_task.done():
        self._start_ws_task()
        assert self._ws_task is not None
        _WS_TASKS.append(self._ws_task)
    return {}


@pytest.fixture(autouse=True)
def _reset_ws_tasks() -> None:
    _WS_TASKS.clear()


async def test_setup_retries_during_outage_do_not_leak_clients(
    hass: HomeAssistant, clients: list[httpx.AsyncClient]
) -> None:
    """Облако недоступно — ни одна попытка настройки не оставляет открытый клиент."""
    entry = _entry(hass)
    with patch.object(
        SberHomeCoordinator, "_async_update_data", AsyncMock(side_effect=UpdateFailed("down"))
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        for _ in range(2):
            await hass.config_entries.async_reload(entry.entry_id)
            await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert len(clients) == 3
    assert _open(clients) == []
    assert _entry_keys(hass, entry) == []


async def test_broken_tokens_close_client(
    hass: HomeAssistant, clients: list[httpx.AsyncClient]
) -> None:
    """Ошибка ещё до создания координатора (неполные токены SMS-входа) закрывает клиент."""
    entry = _entry(
        hass,
        data={CONF_AUTH_METHOD: AUTH_METHOD_CSAFRONT, "csafront_tokens": {"phone": "+7"}},
    )

    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(clients) == 1
    assert _open(clients) == []


async def test_failure_after_first_refresh_releases_everything(
    hass: HomeAssistant, clients: list[httpx.AsyncClient], caplog: pytest.LogCaptureFixture
) -> None:
    """Сбой на позднем шаге: клиент закрыт, WebSocket остановлен, платформы сняты.

    Платформы к этому моменту уже подняты. Если откат их не снимает, повторная
    настройка не может поднять их снова («already been setup») и запись
    остаётся без сущностей.
    """
    entry = _entry(hass, options={"enabled_device_ids": ["dev-1"]})
    with (
        patch.object(SberHomeCoordinator, "_async_update_data", _update_starting_ws),
        patch.object(SberHomeCoordinator, "_run_ws", _never_ending_ws),
    ):
        with patch(
            "custom_components.sberhome.async_update_conflict_issue",
            side_effect=RuntimeError("boom"),
        ):
            await hass.config_entries.async_setup(entry.entry_id)
            await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.SETUP_ERROR
        assert _open(clients) == []
        assert len(_WS_TASKS) == 1
        assert _WS_TASKS[0].done()
        assert _entry_keys(hass, entry) == []

        # Причина устранена — повторная настройка проходит с нуля.
        caplog.clear()
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert "already been setup" not in caplog.text

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert _open(clients) == []


async def test_unload_leaves_no_entry_data_and_reload_works(
    hass: HomeAssistant, clients: list[httpx.AsyncClient]
) -> None:
    """После выгрузки в hass.data нет ничего от записи; reload поднимает её заново."""
    entry = _entry(hass, options={"enabled_device_ids": ["dev-1"]})
    before = set(hass.data)
    with (
        patch.object(SberHomeCoordinator, "_async_update_data", _update_starting_ws),
        patch.object(SberHomeCoordinator, "_run_ws", _never_ending_ws),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        # Обслуживание реестра заводит свои счётчики в hass.data.
        entry.runtime_data._prune_stale_devices()
        assert len(_entry_keys(hass, entry)) == 3

        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert len(clients) == 2
        assert _open(clients) == [clients[1]]
        assert len(_WS_TASKS) == 2
        assert _WS_TASKS[0].done()
        assert not _WS_TASKS[1].done()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert _open(clients) == []
    assert all(task.done() for task in _WS_TASKS)
    residue = [key for key in set(hass.data) - before if entry.entry_id in str(key)]
    assert residue == []
    assert _entry_keys(hass, entry) == []


async def test_coordinator_owns_shared_http_and_shutdown_is_idempotent(
    hass: HomeAssistant,
) -> None:
    """Клиент передаётся координатору при создании и закрывается его остановкой.

    HA останавливает координатор дважды: явно в выгрузке (или откате
    настройки) и ещё раз из ``entry.async_on_unload``. Второй вызов ничего не
    делает.
    """
    entry = MockConfigEntry(domain=DOMAIN, entry_id="owner", options={})
    entry.add_to_hass(hass)
    http = httpx.AsyncClient()
    coordinator = SberHomeCoordinator(
        hass,
        entry,
        AsyncMock(spec=SberAPI),
        AsyncMock(spec=HttpTransport),
        AsyncMock(spec=AuthManager),
        shared_http=http,
    )
    ws_client = AsyncMock()
    coordinator._ws_client = ws_client
    coordinator._ws_task = hass.async_create_background_task(
        asyncio.Event().wait(), name="sberhome test ws"
    )
    ws_task = coordinator._ws_task

    await coordinator.async_shutdown()
    await coordinator.async_shutdown()

    assert http.is_closed
    assert ws_task.done()
    ws_client.stop.assert_awaited_once()
