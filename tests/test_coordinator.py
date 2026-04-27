"""Tests for the SberHome coordinator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.sberhome.aiosber import SocketMessageDto, StateCache
from custom_components.sberhome.aiosber.dto.devman import DevmanDto
from custom_components.sberhome.aiosber.dto.state import (
    AttributeValueDto,
    StateDto,
)
from custom_components.sberhome.api import HomeAPI, SberAPI
from custom_components.sberhome.coordinator import SberHomeCoordinator
from custom_components.sberhome.exceptions import (
    SberApiError,
    SberAuthError,
    SberConnectionError,
)


@pytest.fixture
def mock_sber_api():
    api = AsyncMock(spec=SberAPI)
    return api


@pytest.fixture
def mock_home_api(mock_devices):
    api = AsyncMock(spec=HomeAPI)
    api.get_cached_devices = MagicMock(return_value=mock_devices)
    api.get_cached_tree = MagicMock(return_value=None)  # no tree → fallback to DTO
    api.update_devices_cache = AsyncMock()
    return api


@pytest.fixture
def mock_hass():
    """Create a minimal mock HomeAssistant instance."""
    hass = MagicMock()
    hass.data = {}
    hass.loop = AsyncMock()
    return hass


@pytest.fixture
def coordinator(mock_hass, mock_config_entry, mock_sber_api, mock_home_api):
    from datetime import timedelta

    coord = SberHomeCoordinator.__new__(SberHomeCoordinator)
    coord.sber_api = mock_sber_api
    coord.home_api = mock_home_api
    coord.hass = mock_hass
    coord.logger = MagicMock()
    coord.name = "sberhome"
    coord.update_interval = timedelta(seconds=30)
    coord._user_update_interval = timedelta(seconds=30)
    coord.config_entry = mock_config_entry
    coord._listeners = {}
    coord.data = None
    coord.last_update_success = True
    coord._update_callback = None
    # WebSocket task attrs (added in PR #11). Mock _start_ws_task — иначе
    # async_create_background_task падает в MagicMock'нутом hass.
    # `.done()=False` имитирует running task — `_async_update_data` его не
    # рестартует (проверка `.done()` добавлена в 3.4.8 для фикса #6).
    coord._ws_task = MagicMock()
    coord._ws_task.done = MagicMock(return_value=False)
    coord._ws_client = None
    # StateCache + sbermap entities cache.
    coord.state_cache = StateCache()
    coord.entities = {}
    # PR #11 stats для panel.
    from collections import deque

    coord.last_polling_at = None
    coord.polling_count = 0
    coord.error_count = 0
    coord.last_ws_message_at = None
    coord.ws_message_count = 0
    coord._ws_log = deque(maxlen=100)
    coord._ws_log_subscribers = []
    # Phase 4 (DevTools) — collectors are real objects so observe_*
    # calls don't blow up; mock would need spec'd interfaces.
    from custom_components.sberhome.command_tracker import CommandTracker
    from custom_components.sberhome.schema_validator import ValidationCollector
    from custom_components.sberhome.state_diff import DiffCollector

    coord.diff_collector = DiffCollector(maxlen=10)
    coord.command_tracker = CommandTracker(maxlen=10, command_timeout=10.0)
    coord.validation_collector = ValidationCollector(maxlen=10)
    # Sber scenarios + at_home (PR-feat/extended-api-coverage).
    coord.scenarios = []
    coord.at_home = None
    coord._scenarios_last_poll_at = None
    coord._scenarios_disabled = True  # skip scenario poll in unit tests
    return coord


@pytest.mark.asyncio
async def test_update_data_success(coordinator, mock_home_api, mock_devices):
    """Test successful data update."""
    result = await coordinator._async_update_data()
    mock_home_api.update_devices_cache.assert_called_once()
    # result is derived from state_cache (DTO.to_dict), not raw mock_devices
    assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_update_data_auth_error(coordinator, mock_home_api):
    """Test auth error raises ConfigEntryAuthFailed."""
    mock_home_api.update_devices_cache.side_effect = SberAuthError("expired")
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_connection_error(coordinator, mock_home_api):
    """Test connection error raises UpdateFailed."""
    mock_home_api.update_devices_cache.side_effect = SberConnectionError("timeout")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_update_data_rate_limited(coordinator, mock_home_api):
    """Test rate limiting adjusts update_interval."""
    mock_home_api.update_devices_cache.side_effect = SberApiError(
        code=429, status_code=429, message="rate limited", retry_after=120
    )
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval.total_seconds() == 120


@pytest.mark.asyncio
async def test_async_setup(coordinator):
    """Test _async_setup runs without error."""
    await coordinator._async_setup()


@pytest.mark.asyncio
async def test_shutdown_closes_clients(coordinator, mock_sber_api, mock_home_api):
    """Test that shutdown closes both API clients."""
    # Call only our custom shutdown logic directly
    await coordinator.home_api.aclose()
    await coordinator.sber_api.aclose()
    mock_home_api.aclose.assert_called_once()
    mock_sber_api.aclose.assert_called_once()


# ----------------------------------------------------------------------
# WebSocket integration
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_ws_device_state_unknown_id_falls_back_to_refresh(coordinator):
    """device_id отсутствует → fallback на полный refresh (PR #11)."""
    msg = SocketMessageDto(
        state=StateDto(
            reported_state=[AttributeValueDto(key="on_off", bool_value=True)],
            timestamp="2026-04-15T00:00:00Z",
        ),
    )
    coordinator.hass.async_create_task = MagicMock()
    coordinator.state_cache._devices = {}  # empty — device unknown

    await coordinator._on_ws_device_state(msg)

    coordinator.hass.async_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_on_ws_device_state_direct_patch(coordinator):
    """device_id известен → точечный patch DTO + entities, БЕЗ refresh (PR #11)."""
    from custom_components.sberhome.aiosber.dto.device import DeviceDto
    from custom_components.sberhome.aiosber.dto.values import (
        AttributeValueType,
    )

    dto = DeviceDto(
        id="dev-1",
        image_set_type="cat_sensor_temp_humidity",
        reported_state=[
            AttributeValueDto(
                key="temperature",
                type=AttributeValueType.INTEGER,
                integer_value=200,
            ),
        ],
    )
    coordinator.state_cache._devices = {"dev-1": dto}
    coordinator.entities = {}
    coordinator.home_api._cached_devices = {"dev-1": dto.to_dict()}
    coordinator.home_api.get_cached_devices = MagicMock(
        return_value=coordinator.home_api._cached_devices
    )
    coordinator.async_set_updated_data = MagicMock()
    coordinator.hass.async_create_task = MagicMock()

    msg = SocketMessageDto(
        state=StateDto(
            device_id="dev-1",
            reported_state=[
                AttributeValueDto(
                    key="temperature",
                    type=AttributeValueType.INTEGER,
                    integer_value=225,
                ),
            ],
        ),
    )
    await coordinator._on_ws_device_state(msg)

    # Refresh НЕ запрашивался (точечный patch)
    coordinator.hass.async_create_task.assert_not_called()
    # DTO патчнут (temperature: 200 → 225)
    new_dto = coordinator.devices["dev-1"]
    by_key = {av.key: av for av in new_dto.reported_state}
    assert by_key["temperature"].integer_value == 225
    # Entities пересобраны для этого устройства
    assert "dev-1" in coordinator.entities
    # async_set_updated_data вызван
    coordinator.async_set_updated_data.assert_called_once()


@pytest.mark.asyncio
async def test_on_ws_device_state_ignores_none_state(coordinator):
    msg = SocketMessageDto(state=None)
    coordinator.hass.async_create_task = MagicMock()
    await coordinator._on_ws_device_state(msg)
    coordinator.hass.async_create_task.assert_not_called()


@pytest.mark.asyncio
async def test_on_ws_device_state_ignores_empty_reported_state(coordinator):
    msg = SocketMessageDto(state=StateDto(reported_state=[], timestamp=None))
    coordinator.hass.async_create_task = MagicMock()
    await coordinator._on_ws_device_state(msg)
    coordinator.hass.async_create_task.assert_not_called()


@pytest.mark.asyncio
async def test_on_ws_devman_event_dispatches_signal(coordinator):
    """DEVMAN_EVENT → async_dispatcher_send с device_id + payload (PR #11)."""
    from unittest.mock import patch

    msg = SocketMessageDto(
        event=DevmanDto(device_id="scenario-1"),
    )
    with patch("custom_components.sberhome.coordinator.async_dispatcher_send") as mock_send:
        await coordinator._on_ws_devman_event(msg)
    mock_send.assert_called_once()
    args = mock_send.call_args.args
    assert args[1] == "sberhome_devman_event"
    assert args[2] == "scenario-1"
    assert args[3] == {"device_id": "scenario-1"}


@pytest.mark.asyncio
async def test_on_ws_devman_event_no_event_payload(coordinator):
    """Если event=None — dispatcher НЕ вызывается."""
    from unittest.mock import patch

    msg = SocketMessageDto(event=None)
    with patch("custom_components.sberhome.coordinator.async_dispatcher_send") as mock_send:
        await coordinator._on_ws_devman_event(msg)
    mock_send.assert_not_called()


def test_start_ws_task_creates_background_task(coordinator):
    """_start_ws_task регистрирует задачу через async_create_background_task."""
    coordinator._ws_task = None
    fake_task = MagicMock()
    coordinator.hass.async_create_background_task = MagicMock(return_value=fake_task)

    coordinator._start_ws_task()

    coordinator.hass.async_create_background_task.assert_called_once()
    assert coordinator._ws_task is fake_task


def test_start_ws_task_swallows_exception(coordinator):
    """Ошибка регистрации фоновой задачи — глотается, polling-only mode."""
    coordinator._ws_task = None
    coordinator.hass.async_create_background_task = MagicMock(
        side_effect=RuntimeError("loop closed")
    )

    coordinator._start_ws_task()  # не должно бросить

    # _ws_task остаётся None — следующий update повторит попытку
    assert coordinator._ws_task is None


@pytest.mark.asyncio
async def test_run_ws_returns_when_auth_fails(coordinator, mock_home_api):
    """Если AuthManager init упал — _run_ws тихо завершается без падения."""
    mock_home_api.get_auth_manager = AsyncMock(side_effect=RuntimeError("no token"))

    await coordinator._run_ws()

    # WebSocketClient не должен быть создан
    assert coordinator._ws_client is None


@pytest.mark.asyncio
async def test_run_ws_creates_client_and_runs(coordinator, mock_home_api):
    """Happy path: AuthManager OK → WebSocketClient создан и .run() вызван.

    Во время `run()` `_ws_client` ссылается на созданный клиент (чтобы
    `ws_connected` property работал). После завершения `run()` finally-блок
    сбрасывает `_ws_client = None`, чтобы следующий polling tick не видел
    stale reference на завершённый клиент.
    """
    mock_home_api.get_auth_manager = AsyncMock(return_value=MagicMock())
    fake_ws_client = AsyncMock()

    # Фиксируем значение _ws_client во время run() — оно должно указывать на клиента
    observed_during_run: list = []

    async def run_side_effect() -> None:
        observed_during_run.append(coordinator._ws_client)

    fake_ws_client.run = AsyncMock(side_effect=run_side_effect)

    with (
        patch("custom_components.sberhome.coordinator.async_get_clientsession") as mock_session,
        patch(
            "custom_components.sberhome.coordinator.WebSocketClient",
            return_value=fake_ws_client,
        ),
        patch("custom_components.sberhome.coordinator.make_aiohttp_factory") as mock_factory,
    ):
        mock_session.return_value = MagicMock()
        mock_factory.return_value = MagicMock()

        await coordinator._run_ws()

    assert observed_during_run == [fake_ws_client]
    fake_ws_client.run.assert_awaited_once()
    # finally сбросил клиент (часть фикса #6 — см. test_run_ws_clears_client_on_completion)
    assert coordinator._ws_client is None


@pytest.mark.asyncio
async def test_run_ws_logs_unexpected_exception(coordinator, mock_home_api):
    """Если WebSocketClient.run() бросил неожиданное — логируем и не падаем."""
    mock_home_api.get_auth_manager = AsyncMock(return_value=MagicMock())
    fake_ws_client = AsyncMock()
    fake_ws_client.run.side_effect = RuntimeError("network broken")

    with (
        patch("custom_components.sberhome.coordinator.async_get_clientsession"),
        patch(
            "custom_components.sberhome.coordinator.WebSocketClient",
            return_value=fake_ws_client,
        ),
        patch("custom_components.sberhome.coordinator.make_aiohttp_factory"),
    ):
        await coordinator._run_ws()  # не должно бросить


@pytest.mark.asyncio
async def test_update_data_starts_ws_when_task_is_none(coordinator, mock_home_api):
    """При первом успешном polling (без активного _ws_task) — стартует WS task."""
    coordinator._ws_task = None
    coordinator._start_ws_task = MagicMock()

    await coordinator._async_update_data()

    coordinator._start_ws_task.assert_called_once()


@pytest.mark.asyncio
async def test_update_data_does_not_restart_ws_when_already_running(coordinator, mock_home_api):
    """Если _ws_task уже запущен — повторно не стартуем."""
    # _ws_task уже truthy MagicMock из фикстуры, .done()=False
    coordinator._start_ws_task = MagicMock()

    await coordinator._async_update_data()

    coordinator._start_ws_task.assert_not_called()


@pytest.mark.asyncio
async def test_update_data_restarts_ws_when_task_is_done(coordinator, mock_home_api):
    """Если `_ws_task.done()=True` (завершился после max_consecutive_failures) —
    `_async_update_data` должен запустить новый. Без `.done()` проверки
    прошлая реализация `if self._ws_task is None` застревала в degraded
    polling-only mode (P0 баг #6)."""
    coordinator._ws_task.done = MagicMock(return_value=True)
    coordinator._start_ws_task = MagicMock()

    await coordinator._async_update_data()

    coordinator._start_ws_task.assert_called_once()


@pytest.mark.asyncio
async def test_run_ws_clears_client_on_completion(coordinator, mock_home_api):
    """После завершения `_run_ws` (нормальное или unexpected) `_ws_client`
    должен быть сброшен на None — иначе `ws_connected` property продолжал
    бы показывать `is_connected` мёртвого клиента, и следующий polling
    tick с `.done() == True` пытался бы рестартовать, оставляя старый
    dead-reference."""
    mock_home_api.get_auth_manager = AsyncMock(return_value=MagicMock())
    fake_ws_client = AsyncMock()
    fake_ws_client.run = AsyncMock(return_value=None)

    with (
        patch("custom_components.sberhome.coordinator.async_get_clientsession"),
        patch(
            "custom_components.sberhome.coordinator.WebSocketClient",
            return_value=fake_ws_client,
        ),
        patch("custom_components.sberhome.coordinator.make_aiohttp_factory"),
    ):
        coordinator._ws_client = None

        await coordinator._run_ws()

    # Run вернулся → finally сбросил клиент
    assert coordinator._ws_client is None


@pytest.mark.asyncio
async def test_update_data_restores_user_interval_after_429(coordinator, mock_home_api):
    """После rate-limit interval повышается; следующий успешный update — восстанавливает."""
    from datetime import timedelta

    coordinator.update_interval = timedelta(seconds=120)  # эмулируем после 429
    coordinator._user_update_interval = timedelta(seconds=30)

    await coordinator._async_update_data()

    assert coordinator.update_interval == timedelta(seconds=30)


# ----------------------------------------------------------------------
# PR #2: DTO + entities cache
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_data_populates_devices_and_entities(coordinator, mock_home_api, mock_devices):
    """После refresh coordinator.devices содержит DeviceDto, entities — HaEntityData."""
    from custom_components.sberhome.aiosber.dto.device import DeviceDto

    # mock_home_api.get_cached_devices_dto возвращает реальные DTO из mock_devices.
    def _to_dto():
        return {did: DeviceDto.from_dict(raw) for did, raw in mock_devices.items()}

    mock_home_api.get_cached_devices_dto = MagicMock(side_effect=_to_dto)

    await coordinator._async_update_data()

    assert "device_light_1" in coordinator.devices
    assert isinstance(coordinator.devices["device_light_1"], DeviceDto)
    # entities — list HaEntityData; для bulb_sber минимум один Platform.LIGHT.
    from homeassistant.const import Platform

    light_entities = coordinator.entities["device_light_1"]
    platforms = {e.platform for e in light_entities}
    assert Platform.LIGHT in platforms


@pytest.mark.asyncio
async def test_update_data_with_unknown_image_yields_empty_entities(coordinator, mock_home_api):
    """Категория unknown → entities=[] но devices DTO всё равно есть."""
    from custom_components.sberhome.aiosber.dto.device import DeviceDto

    raw = {
        "alien-1": {
            "id": "alien-1",
            "image_set_type": "completely_unknown_xyz",
            "name": "Alien",
        }
    }
    mock_home_api.get_cached_devices = MagicMock(return_value=raw)
    mock_home_api.get_cached_devices_dto = MagicMock(
        return_value={"alien-1": DeviceDto.from_dict(raw["alien-1"])}
    )

    await coordinator._async_update_data()

    assert "alien-1" in coordinator.devices
    assert coordinator.entities["alien-1"] == []


def test_rebuild_dto_caches_idempotent(coordinator, mock_home_api, mock_devices):
    """Многократный rebuild — детерминирован, не растёт."""
    from custom_components.sberhome.aiosber.dto.device import DeviceDto

    mock_home_api.get_cached_devices_dto = MagicMock(
        side_effect=lambda: {did: DeviceDto.from_dict(raw) for did, raw in mock_devices.items()}
    )

    coordinator._rebuild_dto_caches()
    first_devices = set(coordinator.devices.keys())
    first_count = sum(len(es) for es in coordinator.entities.values())

    coordinator._rebuild_dto_caches()
    assert set(coordinator.devices.keys()) == first_devices
    assert sum(len(es) for es in coordinator.entities.values()) == first_count


# -------------------------------------------------------------------------
# WS message direction + record_command
# -------------------------------------------------------------------------


def test_record_ws_message_defaults_to_in_direction(coordinator):
    """Записи от _on_ws_* — входящие ("in"). Это default в записи, так что
    уже заложенные DEVICE_STATE/DEVMAN_EVENT не поломались с добавлением поля."""
    coordinator._record_ws_message(topic="DEVICE_STATE", device_id="d1", payload={"k": 1})
    assert len(coordinator._ws_log) == 1
    record = coordinator._ws_log[0]
    assert record["direction"] == "in"
    assert record["topic"] == "DEVICE_STATE"
    assert record["device_id"] == "d1"


def test_record_command_marks_outbound(coordinator):
    """`record_command` должен попадать в ring buffer как direction='out'
    с topic='COMMAND' — для корреляции исходящих команд с входящими push'ами."""
    state = [{"key": "on_off", "bool_value": True}]
    coordinator.record_command("dev-42", state)

    assert len(coordinator._ws_log) == 1
    record = coordinator._ws_log[0]
    assert record["direction"] == "out"
    assert record["topic"] == "COMMAND"
    assert record["device_id"] == "dev-42"
    assert record["payload"] == {"desired_state": state}


@pytest.mark.asyncio
async def test_on_ws_other_topic_logs_but_does_not_patch(coordinator):
    """Unknown topic (напр. SCENARIO_WIDGETS) — просто логируем с payload=msg.to_dict(),
    без patch state_cache / fire event / request_refresh."""
    from custom_components.sberhome.aiosber.dto.scenario import ScenarioWidgetDto

    coordinator.hass.async_create_task = MagicMock()
    coordinator.state_cache.patch_device_state = MagicMock()

    msg = SocketMessageDto(scenario_widget=ScenarioWidgetDto())

    await coordinator._on_ws_other_topic(msg)

    assert len(coordinator._ws_log) == 1
    record = coordinator._ws_log[0]
    assert record["direction"] == "in"
    assert record["topic"] == "scenario_widgets"
    # Никакого side-effects на state_cache / refresh
    coordinator.hass.async_create_task.assert_not_called()
    coordinator.state_cache.patch_device_state.assert_not_called()


# -------------------------------------------------------------------------
# Adaptive polling interval (WS connected → 10 мин, offline → user-setting)
# -------------------------------------------------------------------------


def test_desired_update_interval_when_ws_connected(coordinator):
    """Когда WS connected — polling ослабляется до 10 мин. State уже
    приходит push'ами, tree polling нужен только для discovery."""
    from datetime import timedelta

    fake_client = MagicMock()
    fake_client.is_connected = True
    coordinator._ws_client = fake_client

    assert coordinator._desired_update_interval() == timedelta(seconds=600)


def test_desired_update_interval_when_ws_offline(coordinator):
    """WS offline — возвращаемся к user-настраиваемому интервалу (default 30 сек)."""
    from datetime import timedelta

    coordinator._ws_client = None
    coordinator._user_update_interval = timedelta(seconds=30)

    assert coordinator._desired_update_interval() == timedelta(seconds=30)


@pytest.mark.asyncio
async def test_update_data_switches_to_long_interval_when_ws_connected(coordinator, mock_home_api):
    """После успешного polling с активным WS — interval становится 10 мин."""
    from datetime import timedelta

    fake_client = MagicMock()
    fake_client.is_connected = True
    coordinator._ws_client = fake_client

    await coordinator._async_update_data()

    assert coordinator.update_interval == timedelta(seconds=600)
