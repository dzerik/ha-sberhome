"""Tests for __init__.py — panel registration + lifecycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from custom_components.sberhome import (
    CONFIG_SCHEMA,
    _async_register_panel,
    async_migrate_entry,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.exceptions import (
    SberAuthError,
    SberConnectionError,
)

# -----------------------------------------------------------------------------
# CONFIG_SCHEMA — listeners block (v5.5.0)
# -----------------------------------------------------------------------------


def test_config_schema_accepts_listeners_block() -> None:
    config = {
        "sberhome": {
            "listeners": [
                {
                    "slug": "any_time",
                    "name": "Any TIME",
                    "filter": {"trigger_type": "TIME"},
                }
            ]
        }
    }
    validated = CONFIG_SCHEMA(config)
    assert validated["sberhome"]["listeners"][0]["slug"] == "any_time"


def test_config_schema_listeners_optional() -> None:
    """sberhome: с intents но без listeners — ok."""
    config = {
        "sberhome": {
            "intents": [
                {
                    "name": "Утро",
                    "phrases": ["утро"],
                    "actions": [{"type": "ha_event_only"}],
                }
            ]
        }
    }
    validated = CONFIG_SCHEMA(config)
    # listeners либо отсутствует, либо пустой list
    listeners = validated["sberhome"].get("listeners", [])
    assert listeners == []


def test_config_schema_invalid_listener_filter_rejected() -> None:
    config = {
        "sberhome": {
            "listeners": [
                {"slug": "x", "name": "X", "filter": {}},
            ]
        }
    }
    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(config)


@pytest.mark.asyncio
async def test_panel_registration_uses_manifest_version() -> None:
    """`_async_register_panel` должен читать версию из manifest.json через
    `async_get_integration(hass, DOMAIN).version`, а не из захардкоженной
    константы в const.py (которая регулярно отставала от manifest).

    Это не позволяет сломаться cache-buster'у panel JS при апдейтах через
    HACS.
    """
    hass = MagicMock()
    hass.data = {}
    hass.http.async_register_static_paths = AsyncMock()

    integration = MagicMock()
    integration.version = "3.4.3"

    with (
        patch(
            "custom_components.sberhome.async_get_integration",
            AsyncMock(return_value=integration),
        ),
        patch(
            "custom_components.sberhome.async_register_built_in_panel",
        ) as mock_register,
    ):
        await _async_register_panel(hass)

    mock_register.assert_called_once()
    config = mock_register.call_args.kwargs["config"]
    module_url = config["_panel_custom"]["module_url"]
    assert "?v=3.4.3" in module_url, (
        f"module_url должен содержать актуальную версию из manifest, получено: {module_url}"
    )
    assert hass.data[f"{DOMAIN}_panel_registered"] is True


@pytest.mark.asyncio
async def test_panel_registration_idempotent() -> None:
    """Повторный вызов `_async_register_panel` не должен регистрировать
    панель дважды — защита от гонок при одновременной загрузке нескольких
    config entries."""
    hass = MagicMock()
    hass.data = {f"{DOMAIN}_panel_registered": True}
    hass.http.async_register_static_paths = AsyncMock()

    with patch(
        "custom_components.sberhome.async_register_built_in_panel",
    ) as mock_register:
        await _async_register_panel(hass)

    mock_register.assert_not_called()


@pytest.mark.asyncio
async def test_panel_registration_handles_missing_version() -> None:
    """Если по какой-то причине `integration.version` is None,
    cache-buster всё равно должен быть валидной строкой (не упасть на
    `?v=None`)."""
    hass = MagicMock()
    hass.data = {}
    hass.http.async_register_static_paths = AsyncMock()

    integration = MagicMock()
    integration.version = None

    with (
        patch(
            "custom_components.sberhome.async_get_integration",
            AsyncMock(return_value=integration),
        ),
        patch(
            "custom_components.sberhome.async_register_built_in_panel",
        ) as mock_register,
    ):
        await _async_register_panel(hass)

    module_url = mock_register.call_args.kwargs["config"]["_panel_custom"]["module_url"]
    assert "?v=" in module_url
    assert "None" not in module_url


# -----------------------------------------------------------------------------
# async_setup_entry lifecycle — first_refresh + error mapping
# -----------------------------------------------------------------------------


def _patch_setup_dependencies(
    first_refresh_side_effect: BaseException | None = None,
) -> tuple[dict, MagicMock, MagicMock]:
    """Собрать набор патчей для async_setup_entry тестов.

    Возвращает (patchers, http_mock, coord_mock). Shared httpx принадлежит
    координатору: его закрывает coordinator.async_shutdown — и при выгрузке,
    и при откате прерванной настройки.
    """
    http_mock = MagicMock()
    http_mock.aclose = AsyncMock()

    sber_mock = MagicMock()
    sber_mock.aclose = AsyncMock()
    sber_mock.sberid_tokens = MagicMock()

    auth_mock = MagicMock()
    transport_mock = MagicMock()

    coord_mock = MagicMock()
    coord_mock.async_config_entry_first_refresh = AsyncMock(side_effect=first_refresh_side_effect)
    coord_mock.async_shutdown = AsyncMock()

    patchers = {
        "ssl": patch(
            "custom_components.sberhome.async_init_ssl", AsyncMock(return_value=MagicMock())
        ),
        "http_cls": patch("custom_components.sberhome.httpx.AsyncClient", return_value=http_mock),
        "sber_cls": patch("custom_components.sberhome.SberAPI", return_value=sber_mock),
        "auth_cls": patch("custom_components.sberhome.AuthManager", return_value=auth_mock),
        "transport_cls": patch(
            "custom_components.sberhome.HttpTransport", return_value=transport_mock
        ),
        "coord_cls": patch(
            "custom_components.sberhome.SberHomeCoordinator",
            return_value=coord_mock,
        ),
        "panel": patch("custom_components.sberhome._async_register_panel", AsyncMock()),
        "ws_api": patch("custom_components.sberhome.async_setup_websocket_api", MagicMock()),
        "store": patch("custom_components.sberhome.HATokenStore", MagicMock()),
    }
    for p in patchers.values():
        p.start()
    return patchers, http_mock, coord_mock


def _stop_patchers(patchers: dict) -> None:
    for p in patchers.values():
        p.stop()


def _make_entry() -> MagicMock:
    entry = MagicMock()
    entry.data = {"token": {"access_token": "t"}}
    entry.options = {"enabled_device_ids": []}  # opt-in пустой — без forward
    entry.runtime_data = None
    entry.async_on_unload = MagicMock()
    entry.add_update_listener = MagicMock()
    return entry


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    return hass


@pytest.mark.asyncio
async def test_async_setup_entry_waits_for_first_refresh() -> None:
    """`async_config_entry_first_refresh` должен успеть выполниться ДО
    `async_forward_entry_setups`. Иначе платформы создают entities из
    пустого `coordinator.devices` и получают 0 entities (P0 баг)."""
    hass = _make_hass()
    entry = _make_entry()
    # С непустым списком устройств — форвард происходит
    entry.options = {"enabled_device_ids": ["dev_1"]}

    patchers, http_mock, coord_mock = _patch_setup_dependencies()
    try:
        result = await async_setup_entry(hass, entry)
        coord_cls = patchers["coord_cls"].target.SberHomeCoordinator
    finally:
        _stop_patchers(patchers)

    assert result is True
    # runtime_data — уже coordinator (т.е. first_refresh завершился до присваивания)
    assert entry.runtime_data is not None
    # forward вызван ровно один раз с PLATFORMS
    hass.config_entries.async_forward_entry_setups.assert_called_once()
    # Общий клиент передан координатору при создании — он его и закроет.
    assert coord_cls.call_args.kwargs["shared_http"] is http_mock
    http_mock.aclose.assert_not_awaited()
    coord_mock.async_shutdown.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_setup_entry_raises_config_entry_auth_failed() -> None:
    """Если `first_refresh` поднимает `ConfigEntryAuthFailed` (в норме это
    coordinator._async_update_data мапит SberAuthError), `async_setup_entry`
    пробрасывает его — HA запускает reauth flow."""
    hass = _make_hass()
    entry = _make_entry()

    patchers, _, coord_mock = _patch_setup_dependencies(
        first_refresh_side_effect=ConfigEntryAuthFailed("expired"),
    )
    try:
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)
    finally:
        _stop_patchers(patchers)

    # Откат настройки останавливает координатор, а он закрывает shared http.
    coord_mock.async_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_entry_raises_config_entry_not_ready_on_sber_error() -> None:
    """Сырой `SberConnectionError` из `first_refresh` (в обход coordinator
    mapping) превращается в `ConfigEntryNotReady` — HA автоматически
    retry setup."""
    hass = _make_hass()
    entry = _make_entry()

    patchers, _, coord_mock = _patch_setup_dependencies(
        first_refresh_side_effect=SberConnectionError("connection refused"),
    )
    try:
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)
    finally:
        _stop_patchers(patchers)

    coord_mock.async_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_entry_sber_auth_error_also_closes_clients() -> None:
    """Любой SberSmartHomeError (base class) → ConfigEntryNotReady +
    cleanup клиентов. Это защита на случай, если coordinator не поймал
    исключение сам."""
    hass = _make_hass()
    entry = _make_entry()

    patchers, _, coord_mock = _patch_setup_dependencies(
        first_refresh_side_effect=SberAuthError("generic"),
    )
    try:
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)
    finally:
        _stop_patchers(patchers)

    coord_mock.async_shutdown.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [asyncio.CancelledError(), ConfigEntryNotReady("later"), RuntimeError("unexpected")],
    ids=["cancelled", "not_ready", "unexpected"],
)
async def test_async_setup_entry_any_failure_stops_coordinator(error: BaseException) -> None:
    """Любое исключение первого опроса — включая отмену задачи настройки —
    останавливает координатор (клиент, WebSocket, фоновые задачи) и уходит
    в HA без подмены."""
    hass = _make_hass()
    entry = _make_entry()

    patchers, _, coord_mock = _patch_setup_dependencies(first_refresh_side_effect=error)
    try:
        with pytest.raises(type(error)):
            await async_setup_entry(hass, entry)
    finally:
        _stop_patchers(patchers)

    coord_mock.async_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_entry_failure_before_coordinator_closes_http() -> None:
    """Сбой ещё до создания координатора (сломанные данные записи) закрывает
    клиент сам — координатора, который закрыл бы его, ещё нет."""
    hass = _make_hass()
    entry = _make_entry()

    patchers, http_mock, _ = _patch_setup_dependencies()
    try:
        patchers["coord_cls"].target.SberHomeCoordinator.side_effect = KeyError("token")
        with pytest.raises(KeyError):
            await async_setup_entry(hass, entry)
    finally:
        _stop_patchers(patchers)

    http_mock.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_setup_entry_failed_cleanup_keeps_original_error() -> None:
    """Сбой самой уборки не подменяет исходную ошибку: по ней HA решает,
    повторять настройку или просить reauth."""
    hass = _make_hass()
    entry = _make_entry()

    patchers, _, coord_mock = _patch_setup_dependencies(
        first_refresh_side_effect=ConfigEntryAuthFailed("expired"),
    )
    coord_mock.async_shutdown.side_effect = RuntimeError("cleanup failed")
    try:
        with pytest.raises(ConfigEntryAuthFailed):
            await async_setup_entry(hass, entry)
    finally:
        _stop_patchers(patchers)


# -----------------------------------------------------------------------------
# async_unload_entry — coordinator.async_shutdown + panel cleanup
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_unload_entry_calls_coordinator_shutdown() -> None:
    """Unload должен вызвать `coordinator.async_shutdown()` — иначе
    httpx клиенты и WS task остаются живыми (HA вызывает shutdown
    только на hass.stop, не на reload)."""
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    # Есть ещё одна загруженная запись — panel остаётся
    hass.config_entries.async_loaded_entries = MagicMock(return_value=[MagicMock()])
    hass.data = {}

    coord_mock = MagicMock()
    coord_mock.async_shutdown = AsyncMock()

    entry = MagicMock()
    entry.options = {"enabled_device_ids": ["dev_1"]}  # forward = True
    entry.runtime_data = coord_mock

    result = await async_unload_entry(hass, entry)

    assert result is True
    coord_mock.async_shutdown.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_unload_entry_removes_only_its_own_entry_data() -> None:
    """Успешная выгрузка убирает все данные записи из `hass.data`; данные
    другой записи и общие маркеры интеграции остаются."""
    own = {
        f"{DOMAIN}_platforms_forwarded_e1": True,
        f"{DOMAIN}_options_e1": {"enabled_device_ids": ["dev_1"]},
        f"{DOMAIN}_prune_misses_e1": {"dev_2": 1},
    }
    foreign = {
        f"{DOMAIN}_options_e2": {},
        f"{DOMAIN}_prune_misses_e2": {},
        f"{DOMAIN}_services_registered": True,
    }
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_loaded_entries = MagicMock(return_value=[MagicMock()])
    hass.data = {**own, **foreign}

    entry = MagicMock(entry_id="e1", options={"enabled_device_ids": ["dev_1"]})
    entry.runtime_data = MagicMock(async_shutdown=AsyncMock())

    assert await async_unload_entry(hass, entry) is True
    assert hass.data == foreign


@pytest.mark.asyncio
async def test_async_unload_entry_keeps_entry_data_when_unload_fails() -> None:
    """Запись не выгрузилась и продолжает работать — её данные не трогаем,
    иначе следующая попытка выгрузки не узнает, были ли подняты платформы."""
    data = {
        f"{DOMAIN}_platforms_forwarded_e1": True,
        f"{DOMAIN}_options_e1": {"enabled_device_ids": ["dev_1"]},
    }
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    hass.config_entries.async_loaded_entries = MagicMock(return_value=[MagicMock()])
    hass.data = dict(data)

    entry = MagicMock(entry_id="e1", options={"enabled_device_ids": []})
    entry.runtime_data = MagicMock(async_shutdown=AsyncMock())

    assert await async_unload_entry(hass, entry) is False
    assert hass.data == data


@pytest.mark.asyncio
async def test_async_unload_entry_skips_shutdown_on_failed_unload() -> None:
    """Если `async_unload_platforms` вернул False (платформа не выгрузилась),
    `coordinator.async_shutdown()` НЕ вызывается — entry остаётся живым,
    закрывать httpx преждевременно нельзя."""
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)
    hass.config_entries.async_loaded_entries = MagicMock(return_value=[])
    hass.data = {}

    coord_mock = MagicMock()
    coord_mock.async_shutdown = AsyncMock()

    entry = MagicMock()
    entry.options = {"enabled_device_ids": ["dev_1"]}
    entry.runtime_data = coord_mock

    result = await async_unload_entry(hass, entry)

    assert result is False
    coord_mock.async_shutdown.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_unload_entry_removes_panel_marker_on_last() -> None:
    """При unload ПОСЛЕДНЕГО config entry интеграция снимает panel
    и очищает marker в `hass.data`. Без очистки marker'а повторное
    добавление integration не зарегистрирует panel снова (idempotent
    check в `_async_register_panel`)."""
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_loaded_entries = MagicMock(return_value=[])
    hass.data = {f"{DOMAIN}_panel_registered": True}

    coord_mock = MagicMock()
    coord_mock.async_shutdown = AsyncMock()

    entry = MagicMock()
    entry.options = {"enabled_device_ids": ["dev_1"]}
    entry.runtime_data = coord_mock

    with patch("custom_components.sberhome.async_remove_panel") as mock_remove:
        result = await async_unload_entry(hass, entry)

    assert result is True
    mock_remove.assert_called_once()
    assert f"{DOMAIN}_panel_registered" not in hass.data


@pytest.mark.asyncio
async def test_async_unload_entry_without_forwarded_platforms() -> None:
    """Для opt-in установки (enabled_device_ids=[]) форвард не был
    сделан → unload не пытается их выгружать, но всё равно закрывает
    coordinator."""
    hass = MagicMock()
    hass.config_entries.async_unload_platforms = AsyncMock()
    hass.config_entries.async_loaded_entries = MagicMock(return_value=[MagicMock()])
    hass.data = {}

    coord_mock = MagicMock()
    coord_mock.async_shutdown = AsyncMock()

    entry = MagicMock()
    entry.options = {"enabled_device_ids": []}
    entry.runtime_data = coord_mock

    result = await async_unload_entry(hass, entry)

    assert result is True
    # platforms не форвардили — их и не выгружаем
    hass.config_entries.async_unload_platforms.assert_not_called()
    # но clients закрываем
    coord_mock.async_shutdown.assert_awaited_once()


# -----------------------------------------------------------------------------
# async_migrate_entry — v1 → v2 (legacy token format normalization)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_to_v2_converts_expires_at() -> None:
    """Legacy authlib-токен (`expires_at` absolute) конвертится в
    aiosber-стиль (`obtained_at`). Это убирает необходимость в
    `_normalize_legacy_token` runtime compat-слое."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    entry = MagicMock()
    entry.version = 1
    entry.data = {
        "token": {
            "access_token": "at",
            "refresh_token": "rt",
            "expires_at": 1_700_003_600,  # legacy absolute timestamp
            "expires_in": 3600,
        }
    }

    result = await async_migrate_entry(hass, entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_called_once()
    call = hass.config_entries.async_update_entry.call_args
    new_data = call.kwargs["data"]
    token = new_data["token"]
    assert "obtained_at" in token
    assert token["obtained_at"] == 1_700_000_000  # expires_at - expires_in
    assert "expires_at" not in token
    assert call.kwargs["version"] == 2


@pytest.mark.asyncio
async def test_async_migrate_entry_v2_is_noop() -> None:
    """Если entry уже v2 — migrate ничего не делает."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    entry = MagicMock()
    entry.version = 2
    entry.data = {"token": {"access_token": "at", "obtained_at": 1_700_000_000}}

    result = await async_migrate_entry(hass, entry)

    assert result is True
    hass.config_entries.async_update_entry.assert_not_called()


@pytest.mark.asyncio
async def test_async_migrate_entry_v1_without_expires_at_still_bumps() -> None:
    """Если legacy entry уже имеет obtained_at (повторная миграция),
    бамп версии всё равно происходит, token не перезаписывается."""
    hass = MagicMock()
    hass.config_entries.async_update_entry = MagicMock()

    entry = MagicMock()
    entry.version = 1
    entry.data = {
        "token": {
            "access_token": "at",
            "obtained_at": 1_700_000_000,  # уже нормализован
            "expires_in": 3600,
        }
    }

    result = await async_migrate_entry(hass, entry)

    assert result is True
    # update вызван для bump версии, но token не менялся
    call = hass.config_entries.async_update_entry.call_args
    assert call.kwargs["version"] == 2
    assert call.kwargs["data"]["token"]["obtained_at"] == 1_700_000_000
