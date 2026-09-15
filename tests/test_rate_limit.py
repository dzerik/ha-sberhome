"""Ответ 429 от облака Сбера замедляет опрос, а не долбит облако дальше.

Раньше ответ «слишком много запросов» превращался в обычную ошибку опроса:
следующий опрос уходил через штатный интервал (30 с без WebSocket), даже если
облако просило подождать дольше, а фоновые опросы после первого 429
отключались до ручного «Обновить», как сломанные.

Проверяется поведение целиком: настоящий координатор, настоящий HTTP-транспорт
поверх подменённой сети и расписание опросов Home Assistant.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from email.utils import format_datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.sberhome import coordinator as coordinator_module
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.exceptions import NetworkError, RateLimitError
from custom_components.sberhome.aiosber.transport import HttpTransport
from custom_components.sberhome.api import SberAPI
from custom_components.sberhome.const import DEFAULT_SCAN_INTERVAL, DOMAIN
from custom_components.sberhome.coordinator import SberHomeCoordinator, ThrottledPoll

ENTRY_ID = "rate-limit-entry"


class _Cloud:
    """Подменённое облако: отвечает заданным статусом и считает запросы."""

    def __init__(self) -> None:
        self.status = 429
        self.headers: dict[str, str] = {}
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        if self.status == 200:
            return httpx.Response(200, json={"result": []})
        return httpx.Response(self.status, json={"message": "slow down"}, headers=self.headers)


@pytest.fixture
def cloud() -> _Cloud:
    return _Cloud()


@pytest.fixture
async def coordinator(hass: HomeAssistant, cloud: _Cloud) -> SberHomeCoordinator:
    """Настоящий координатор, чьи запросы уходят в подменённое облако."""
    entry = MockConfigEntry(domain=DOMAIN, entry_id=ENTRY_ID, options={})
    entry.add_to_hass(hass)
    http = httpx.AsyncClient(transport=httpx.MockTransport(cloud))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="TOK", expires_in=86400))
    auth = AuthManager(http=http, store=store)
    coord = SberHomeCoordinator(
        hass,
        entry,
        AsyncMock(spec=SberAPI),
        HttpTransport(http=http, auth=auth),
        auth,
    )
    # Фоновые опросы — вне этого файла, кроме отдельных тестов ниже.
    for poll in coord._background_polls():
        poll.disabled = True
    # WebSocket после успешного опроса не нужен: сеть подменена только для REST.
    coord._start_ws_task = MagicMock()
    yield coord
    await http.aclose()


async def _advance(hass: HomeAssistant, freezer: FrozenDateTimeFactory, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # Плановый опрос идёт фоновой задачей записи: hass.async_block_till_done
    # её не ждёт, а настоящий HTTP-транспорт не завершается за один шаг цикла.
    entry = hass.config_entries.async_get_entry(ENTRY_ID)
    if entry is not None and (tasks := list(entry._background_tasks)):
        await asyncio.wait(tasks)


async def _throttled_refresh(
    hass: HomeAssistant, coordinator: SberHomeCoordinator, cloud: _Cloud
) -> tuple[MagicMock, int]:
    """Подписаться (чтобы опрос планировался) и получить первый 429."""
    unsub = coordinator.async_add_listener(MagicMock())
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False
    assert cloud.requests > 0
    return unsub, cloud.requests


async def test_retry_after_seconds_postpones_next_poll(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
) -> None:
    """Retry-After: 120 — ни одного запроса к облаку раньше, чем через 120 с."""
    cloud.headers = {"Retry-After": "120"}
    unsub, after_first = await _throttled_refresh(hass, coordinator, cloud)

    await _advance(hass, freezer, DEFAULT_SCAN_INTERVAL + 1)
    # До 118.5 с: планировщик HA вправе сработать до секунды раньше, а
    # async_fire_time_changed запускает таймеры ещё на 0.5 с раньше.
    await _advance(hass, freezer, 117.5 - DEFAULT_SCAN_INTERVAL)
    assert cloud.requests == after_first

    cloud.status = 200
    await _advance(hass, freezer, 3)
    assert cloud.requests > after_first
    assert coordinator.last_update_success is True
    unsub()


def _align_clock(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, coordinator: SberHomeCoordinator
) -> None:
    """Худший для планировщика HA случай: часы на ``N.9`` с, доля секунды 0.05.

    HA ставит плановый опрос на ``int(loop.time()) + доля + интервал`` — такой
    опрос срабатывает на 0.85 с раньше конца паузы, начатой в ``N.9``.
    """
    coordinator._microsecond = 0.05
    freezer.tick(timedelta(seconds=(0.9 - hass.loop.time() % 1) % 1))


@pytest.mark.parametrize("supports_retry_after", [True, False], ids=["new_ha", "old_ha"])
async def test_poll_scheduled_just_before_pause_end_reaches_cloud(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    monkeypatch: pytest.MonkeyPatch,
    supports_retry_after: bool,
) -> None:
    """Плановый опрос, сработавший чуть раньше конца паузы, всё же идёт в облако.

    Раньше он считался «внутри паузы» и откладывался ещё на полный интервал:
    устройства возвращались через 150 с вместо 120.
    """
    monkeypatch.setattr(
        coordinator_module, "_UPDATE_FAILED_SUPPORTS_RETRY_AFTER", supports_retry_after
    )
    _align_clock(hass, freezer, coordinator)
    cloud.headers = {"Retry-After": "120"}
    unsub, after_first = await _throttled_refresh(hass, coordinator, cloud)

    # Опрос стоит на 119.15 с; async_fire_time_changed запускает таймеры с
    # опережением 0.5 с, так что к 118.5 с он ещё не сработал.
    await _advance(hass, freezer, 118.5)
    assert cloud.requests == after_first

    # Срабатывает на 119.2 с — за 0.8 с до конца паузы.
    cloud.status = 200
    await _advance(hass, freezer, 0.7)
    assert cloud.requests > after_first
    assert coordinator.last_update_success is True
    unsub()


async def test_refresh_near_pause_end_does_not_add_full_interval(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
) -> None:
    """«Обновить» под конец паузы при живом WebSocket (интервал 10 мин).

    Отклонённый внутри паузы опрос переносит следующий на конец паузы, а не на
    10 минут вперёд.
    """
    ws = MagicMock()
    ws.is_connected = True
    coordinator._ws_client = ws
    coordinator.update_interval = timedelta(seconds=600)
    cloud.headers = {"Retry-After": "900"}
    unsub, after_first = await _throttled_refresh(hass, coordinator, cloud)

    await _advance(hass, freezer, 850)
    await coordinator.async_refresh()
    assert cloud.requests == after_first

    cloud.status = 200
    await _advance(hass, freezer, 52)
    assert cloud.requests > after_first
    assert coordinator.last_update_success is True
    unsub()


async def test_retry_after_http_date_postpones_next_poll(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
) -> None:
    """Retry-After в виде даты HTTP — ждём до этой даты, а не штатный интервал."""
    retry_at = dt_util.utcnow() + timedelta(seconds=300)
    cloud.headers = {"Retry-After": format_datetime(retry_at, usegmt=True)}
    unsub, after_first = await _throttled_refresh(hass, coordinator, cloud)

    for _ in range(9):
        await _advance(hass, freezer, 32)
    assert cloud.requests == after_first

    cloud.status = 200
    await _advance(hass, freezer, 15)
    assert cloud.requests > after_first
    unsub()


async def test_refresh_requested_inside_window_does_not_reach_cloud(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
) -> None:
    """«Обновить» в панели или переподключение WebSocket не обходят паузу."""
    cloud.headers = {"Retry-After": "600"}
    unsub, after_first = await _throttled_refresh(hass, coordinator, cloud)

    await _advance(hass, freezer, 60)
    await coordinator.async_refresh()
    assert cloud.requests == after_first
    assert coordinator.consecutive_failures == 1
    unsub()


async def test_rate_limit_warning_is_logged_once_per_episode(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    caplog: pytest.LogCaptureFixture,
) -> None:
    cloud.headers = {"Retry-After": "40"}
    unsub, _ = await _throttled_refresh(hass, coordinator, cloud)
    await _advance(hass, freezer, 41)
    await _advance(hass, freezer, 41)
    assert cloud.requests >= 3 * 4  # три опроса подряд получили 429

    warnings = [r for r in caplog.records if "ограничило частоту" in r.getMessage()]
    assert len(warnings) == 1
    unsub()


async def test_rate_limit_without_retry_after_still_backs_off(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
) -> None:
    """Без заголовка — пауза по умолчанию, а не штатный 30-секундный интервал."""
    unsub, after_first = await _throttled_refresh(hass, coordinator, cloud)

    # С запасом на опережение планировщика HA и async_fire_time_changed.
    await _advance(hass, freezer, coordinator_module.RATE_LIMIT_DEFAULT_BACKOFF_SEC - 1.5)
    assert cloud.requests == after_first
    unsub()


async def test_retry_after_is_capped(coordinator: SberHomeCoordinator) -> None:
    """Заголовок «приходите через неделю» не выключает опрос на неделю."""
    coordinator.client.device_service.refresh = AsyncMock(
        side_effect=RateLimitError(retry_after=7 * 86400)
    )
    with pytest.raises(coordinator_module.UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.retry_after == coordinator_module.RATE_LIMIT_MAX_BACKOFF_SEC


async def test_short_retry_after_does_not_speed_up_polling(
    coordinator: SberHomeCoordinator,
) -> None:
    """Retry-After короче интервала опроса не делает опрос чаще обычного."""
    ws = MagicMock()
    ws.is_connected = True
    coordinator._ws_client = ws
    coordinator.client.device_service.refresh = AsyncMock(side_effect=RateLimitError(retry_after=5))
    with pytest.raises(coordinator_module.UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.retry_after == 600


async def test_old_home_assistant_extends_interval_and_restores_it(
    coordinator: SberHomeCoordinator,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HA без ``UpdateFailed(retry_after=)``: интервал растягивается и возвращается."""
    monkeypatch.setattr(coordinator_module, "_UPDATE_FAILED_SUPPORTS_RETRY_AFTER", False)
    coordinator.client.device_service.refresh = AsyncMock(
        side_effect=RateLimitError(retry_after=240)
    )
    with pytest.raises(coordinator_module.UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.retry_after is None
    assert coordinator.update_interval == timedelta(seconds=240)

    freezer.tick(timedelta(seconds=241))
    coordinator.client.device_service.refresh = AsyncMock()
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


async def test_old_home_assistant_short_pause_does_not_shrink_interval(
    coordinator: SberHomeCoordinator,
    freezer: FrozenDateTimeFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Старый HA: опрос под конец паузы не оставляет интервал в пару секунд."""
    monkeypatch.setattr(coordinator_module, "_UPDATE_FAILED_SUPPORTS_RETRY_AFTER", False)
    coordinator.client.device_service.refresh = AsyncMock(
        side_effect=RateLimitError(retry_after=40)
    )
    with pytest.raises(coordinator_module.UpdateFailed):
        await coordinator._async_update_data()

    # «Обновить» за 5 с до конца паузы — следующий опрос к концу паузы.
    freezer.tick(timedelta(seconds=35))
    with pytest.raises(coordinator_module.UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=5)

    # Новый 429 с коротким Retry-After — не чаще штатного интервала.
    freezer.tick(timedelta(seconds=6))
    coordinator.client.device_service.refresh = AsyncMock(side_effect=RateLimitError(retry_after=2))
    with pytest.raises(coordinator_module.UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)


@pytest.mark.parametrize("supports_retry_after", [True, False], ids=["new_ha", "old_ha"])
async def test_error_after_short_rejection_keeps_normal_cadence(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    monkeypatch: pytest.MonkeyPatch,
    supports_retry_after: bool,
) -> None:
    """«Обновить» за 2 с до конца паузы, затем облако отвечает 503.

    На старом HA отклонённый опрос сжимал интервал до 2 с, а вернуть штатный
    мог только успешный опрос: пока облако отвечало ошибкой, запросы шли
    каждые 2 секунды.
    """
    monkeypatch.setattr(
        coordinator_module, "_UPDATE_FAILED_SUPPORTS_RETRY_AFTER", supports_retry_after
    )
    cloud.headers = {"Retry-After": "40"}
    unsub, after_first = await _throttled_refresh(hass, coordinator, cloud)

    await _advance(hass, freezer, 38)
    await coordinator.async_refresh()
    assert cloud.requests == after_first

    cloud.status = 503
    cloud.headers = {}
    await _advance(hass, freezer, 3)
    after_error = cloud.requests
    assert after_error > after_first
    assert coordinator.last_update_success is False
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    # Следующий опрос — через штатный интервал, а не через 2 секунды.
    await _advance(hass, freezer, DEFAULT_SCAN_INTERVAL - 3)
    assert cloud.requests == after_error

    await _advance(hass, freezer, 5)
    assert cloud.requests > after_error
    unsub()


async def test_other_errors_keep_normal_schedule(coordinator: SberHomeCoordinator) -> None:
    coordinator.client.device_service.refresh = AsyncMock(side_effect=NetworkError("dns"))
    with pytest.raises(coordinator_module.UpdateFailed) as exc:
        await coordinator._async_update_data()
    assert exc.value.retry_after is None
    assert coordinator.update_interval == timedelta(seconds=DEFAULT_SCAN_INTERVAL)

    # И следующая попытка идёт сразу, без паузы.
    coordinator.client.device_service.refresh = AsyncMock()
    await coordinator._async_update_data()
    coordinator.client.device_service.refresh.assert_awaited_once()


# ---------------------------------------------------------------------------
# Фоновые опросы
# ---------------------------------------------------------------------------


async def test_background_poll_is_postponed_not_disabled(coordinator: SberHomeCoordinator) -> None:
    poll = ThrottledPoll(60, "Scenario")

    async def throttled() -> None:
        raise RateLimitError(retry_after=900)

    await coordinator._throttled_poll(poll, throttled)
    assert poll.disabled is False
    assert poll.last_error is None
    assert poll.last_poll_at is not None
    assert poll.due(poll.last_poll_at + 899) is False
    assert poll.due(poll.last_poll_at + 901) is True


async def test_discovery_stops_on_rate_limit_and_is_postponed(
    coordinator: SberHomeCoordinator,
) -> None:
    """Discovery не перебирает остальные хабы под 429 и не отключается."""
    coordinator._discover_poll.disabled = False
    coordinator._hub_device_ids = MagicMock(return_value=["hub-1", "hub-2"])
    api = MagicMock()
    api.discover = AsyncMock(side_effect=RateLimitError(retry_after=300))
    coordinator._device_api = MagicMock(return_value=api)

    await coordinator._maybe_poll_discovery()

    assert api.discover.await_count == 1
    assert coordinator._discover_poll.disabled is False
    now = coordinator._discover_poll.last_poll_at
    assert coordinator._discover_poll.due(now + 3601) is True
    coordinator._discover_poll.interval = 1
    assert coordinator._discover_poll.due(now + 299) is False


async def test_staros_poll_respects_retry_after(coordinator: SberHomeCoordinator) -> None:
    coordinator._staros_api = MagicMock()
    coordinator._staros_poll.disabled = False
    coordinator._staros_poll.interval = 60
    coordinator._refresh_staros = AsyncMock(side_effect=RateLimitError(retry_after=500))

    await coordinator._maybe_poll_staros()

    now = coordinator._staros_poll.last_poll_at
    assert coordinator._staros_api is not None
    assert coordinator._staros_poll.due(now + 61) is False
    assert coordinator._staros_poll.due(now + 501) is True
