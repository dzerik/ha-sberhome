"""DataUpdateCoordinator for SberHome.

Поддерживает два режима получения обновлений:
- **Polling** (всегда) — periodic refresh через `_async_update_data()`.
- **WebSocket push** (если доступен) — `wss://ws.iot.sberdevices.ru` с
  диспетчеризацией DEVICE_STATE → patch локального state + async_set_updated_data.

WS — additive: polling остаётся как fallback при разрыве соединения.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import deque
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from ._ws_adapter import make_aiohttp_factory
from .aiosber import SberClient, SocketMessageDto, StateCache, Topic, TopicRouter, WebSocketClient
from .aiosber.api import DeviceAPI, IndicatorAPI, InventoryAPI, ScenarioAPI
from .aiosber.dto import IndicatorColor, IndicatorColors
from .aiosber.dto.device import DeviceDto
from .aiosber.dto.scenario import ScenarioDto, ScenarioEventDto
from .aiosber.dto.union import UnionDto
from .api import HomeAPI, SberAPI
from .command_tracker import CommandTracker
from .const import (
    CONF_ENABLED_DEVICE_IDS,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    LOGGER,
    WS_CONNECTED_SCAN_INTERVAL,
)
from .exceptions import (
    SberApiError,
    SberAuthError,
    SberConnectionError,
    SberSmartHomeError,
)
from .sbermap import (
    HaEntityData,
    map_device_to_entities,
)
from .schema_validator import ValidationCollector
from .state_diff import DiffCollector

# Dispatcher signal для DEVMAN_EVENT push'ей. Event entities подписываются
# в `async_added_to_hass`, fire HA event bus при получении.
SIGNAL_DEVMAN_EVENT = f"{DOMAIN}_devman_event"

# HA Event bus name для voice-intents (Phase 10). Срабатывает на каждый
# Sber-сценарий (любого типа), который выполнился. Payload:
# {scenario_id, name, event_time, type, account_id}.
EVENT_SBERHOME_INTENT = f"{DOMAIN}_intent"

# Limit для GET /scenario/v2/event при WS-триггере — берём последние N
# события и фильтруем уже обработанные. 10 более чем достаточно: между
# scenario_widgets WS push и нашим fetch'ом редко кто успевает накидать
# больше 1-2 новых.
INTENT_FETCH_LIMIT = 10

# Cooldown между intent fetch'ами — guard от scenario_widgets-флуда
# (Sber дублирует UPDATE_WIDGETS push'ы парами). 1 sec достаточно
# чтобы погасить duplicate, но не пропустить быстрые повторные команды.
INTENT_DISPATCH_COOLDOWN_SEC = 1.0

# Интервал между poll'ами /scenario/v2/scenario + /scenario/v2/home/variable/at_home.
# 5 минут — список сценариев меняется редко (CRUD руками пользователя),
# at_home чаще, но HA-side switch.set_at_home делает optimistic update,
# так что чтение нужно только для side-effect detection.
SCENARIO_POLL_INTERVAL_SEC = 300

# Polling cadence для /inventory/ota-upgrades — реже чем сценарии:
# OTA-релизы выходят редко (раз в недели), но проверка раз в час даёт
# приемлемый latency показывая «доступное обновление» в HA UI.
OTA_POLL_INTERVAL_SEC = 3600

# /devices/{id}/discovery — для bridges/hubs возвращает список paired
# sub-devices + статусы. Меняется при добавлении нового устройства,
# что редко; раз в час достаточно для diagnostic visibility.
DISCOVER_POLL_INTERVAL_SEC = 3600

# /devices/indicator/values — настройки LED-индикатора колонок. Меняется
# редко (только из приложения Sber пользователем); часовой poll даёт
# свежие данные без нагрузки.
INDICATOR_POLL_INTERVAL_SEC = 3600

# Категории, которые рассматриваются как «хабы» — для них дёргается
# /devices/{id}/discovery. Sber-speaker (SberBoom Home) выступает как
# Zigbee+Matter hub, intercom иногда несёт sub-streams.
HUB_CATEGORIES: frozenset[str] = frozenset({"hub", "sber_speaker", "intercom"})

type SberHomeConfigEntry = ConfigEntry[SberHomeCoordinator]


class SberHomeCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to manage fetching SberHome data."""

    config_entry: SberHomeConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: SberHomeConfigEntry,
        sber_api: SberAPI,
        home_api: HomeAPI,
    ) -> None:
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.sber_api = sber_api
        self.home_api = home_api
        self._user_update_interval = timedelta(seconds=scan_interval)
        # WebSocket — lazy, после первого успешного polling refresh.
        self._ws_client: WebSocketClient | None = None
        self._ws_task: asyncio.Task | None = None
        # Shared httpx.AsyncClient injected by `async_setup_entry` — один
        # pool на оба SberAPI/HomeAPI. Закрывается в async_shutdown.
        self._shared_http: httpx.AsyncClient | None = None
        # StateCache — typed single source of truth (devices + groups + rooms).
        self.state_cache = StateCache()
        # sbermap entities cache (rebuilt from state_cache after each refresh).
        self.entities: dict[str, list[HaEntityData]] = {}
        # Stats для panel (PR #12) — count + last timestamps + ring buffer WS msgs.
        self.last_polling_at: float | None = None
        self.last_ws_message_at: float | None = None
        self.polling_count: int = 0
        self.error_count: int = 0
        self.ws_message_count: int = 0
        self._ws_log: deque[dict[str, Any]] = deque(maxlen=100)
        self._ws_log_subscribers: list[Callable[[dict[str, Any]], None]] = []
        # DevTools #1: per-device state-payload diff collector.  Fed by
        # every WS DEVICE_STATE push and by polling refresh; empty deltas
        # (identical-to-prior) are dropped so the DevTools log shows only
        # real changes.
        self.diff_collector = DiffCollector(maxlen=200)
        # DevTools #5: schema validator — catches API drift by checking
        # every inbound reported_state against AttributeValueType enum
        # + known AttrKey list.  Unknown keys and malformed type/value
        # pairs surface as warnings instead of silently producing None
        # typed accessors.
        self.validation_collector = ValidationCollector(maxlen=500)
        # DevTools #4: outbound command tracker.  Each PUT /state is
        # recorded; subsequent reported_state observations confirm (or
        # time out, "silent_rejection") the command.  Sber protocol has
        # no correlation id, so this is how we detect when a command
        # was accepted-by-HTTP but not-applied-by-device.
        self.command_tracker = CommandTracker(maxlen=200, command_timeout=10.0)
        # Sber scenarios + at_home variable. Поллятся раз в N tick'ов
        # (см. _SCENARIO_POLL_INTERVAL_SEC ниже) — отдельно от device tree,
        # чтобы не нагружать API: список меняется редко (CRUD руками
        # пользователя), и быстрая реактивность здесь не нужна.
        self.scenarios: list[ScenarioDto] = []
        self.at_home: bool | None = None
        self._scenarios_last_poll_at: float | None = None
        # Best-effort флаг: ScenarioAPI отвалился — больше не пытаемся
        # пока ошибка возникает регулярно (избегаем шум в логах).
        self._scenarios_disabled: bool = False
        # OTA upgrades: device_id → upgrade_info dict из /inventory/ota-upgrades.
        # Используется UpdateEntity per-device. Pull cadence см.
        # OTA_POLL_INTERVAL_SEC.
        self.ota_upgrades: dict[str, Any] = {}
        self._ota_last_poll_at: float | None = None
        self._ota_disabled: bool = False
        # /devices/{id}/discovery results: device_id → discovery dict.
        # Зайдём только для hub-устройств (см. HUB_CATEGORIES).
        # Diagnostic-only, exposed via sensor platform для visibility.
        self.discovery_info: dict[str, dict[str, Any]] = {}
        self._discover_last_poll_at: float | None = None
        self._discover_disabled: bool = False
        # Sber-wide LED indicator colors — настройки кольца на колонках.
        # Не per-device, а одна настройка на аккаунт (как в мобильном app).
        self.indicator_colors: IndicatorColors | None = None
        self._indicator_last_poll_at: float | None = None
        self._indicator_disabled: bool = False
        # SberClient — lazily-built фасад поверх home_api._transport.
        # Закрывает архитектурный долг (CLAUDE.md, парадигма пункт 6:
        # «один публичный фасад SberClient для 80% задач») без ломающего
        # рефакторинга HomeAPI. Все internal API-factories (_device_api,
        # _inventory_api, ...) теперь делегируют сюда.
        self._client: SberClient | None = None
        # Voice-intent dispatcher state (Phase 10).
        # Хранит ISO-8601 `event_time` последнего обработанного scenario
        # event'а — нужен для dedup'а: scenario_widgets WS push приходит
        # парами (×2) на каждое срабатывание, плюс при `_on_ws_scenario_widgets`
        # мы получаем последние N событий (limit=10), некоторые из которых
        # уже обработаны.
        self._last_intent_event_time: str | None = None
        # Concurrency: WS пушит UPDATE_WIDGETS дважды подряд за <100ms,
        # одна history-fetch достаточна. Lock держим на время fetch'а.
        self._intent_dispatch_lock = asyncio.Lock()

    @property
    def devices(self) -> dict[str, DeviceDto]:
        """Typed device cache — делегирует к StateCache."""
        return self.state_cache.get_all_devices()

    @property
    def groups(self) -> dict[str, UnionDto]:
        """Typed group cache — делегирует к StateCache."""
        return self.state_cache.get_all_groups()

    @property
    def ws_connected(self) -> bool:
        """WS connection status for panel."""
        return self._ws_client.is_connected if self._ws_client is not None else False

    @property
    def auth_manager(self):
        """AuthManager for token info (panel status)."""
        return self.home_api._auth

    @property
    def client(self) -> SberClient:
        """SberClient facade — lazily построен поверх home_api._transport.

        Это **public entry point** для всех новых Sber-API вызовов в
        coordinator/WS endpoints (`coordinator.client.devices.list()`,
        `coordinator.client.scenarios.execute_command(...)` и т.п.).

        Lifecycle: SberClient НЕ владеет transport — closing'ом transport
        управляет home_api.aclose(). Поэтому coordinator.client.aclose()
        НЕ зовём — закрытие через `home_api.aclose()` в async_shutdown.
        """
        if self._client is None:
            self._client = SberClient(transport=self.home_api._transport)
        return self._client

    @property
    def enum_dictionary(self) -> dict[str, list[str]]:
        """Sber enum reference (`/devices/enums`).

        Подтягивается best-effort при первом успешном refresh; пуст
        пока что-то не вернулось. Используется как fallback-источник для
        select.options там, где `device.attributes[].enum_values` пуст
        (Sber не всегда инлайнит enum в DTO).
        """
        return self.home_api.get_cached_enums()

    def enum_values_for(self, attribute_key: str) -> list[str]:
        """Shortcut: список enum-значений для конкретного attribute_key."""
        return self.home_api.get_enum_values(attribute_key)

    async def _async_setup(self) -> None:
        """Perform initial setup on first coordinator refresh."""
        LOGGER.debug("Coordinator initial setup complete")

    def _desired_update_interval(self) -> timedelta:
        """Интервал polling в зависимости от WS connection state.

        WS доставляет `DEVICE_STATE` push'ами — state changes приходят
        мгновенно. Tree polling нужен только для:
        - Discovery новых устройств (WS не шлёт device add/remove).
        - Rename устройств/комнат, group changes.
        - Safety net если WS молча упадёт (помимо reconnect loop).

        Возвращает `WS_CONNECTED_SCAN_INTERVAL` когда WS жив (10 мин),
        `_user_update_interval` когда WS offline (user-setting, default 30 сек).
        """
        if self.ws_connected:
            return timedelta(seconds=WS_CONNECTED_SCAN_INTERVAL)
        return self._user_update_interval

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the SberHome API."""
        try:
            await self.home_api.update_devices_cache()
            LOGGER.debug(
                "Updated %d devices from API",
                len(self.state_cache.get_all_devices()),
            )
            self.last_polling_at = time.time()
            self.polling_count += 1
            # Параллельно строим типизированные DTO + кэш sbermap-сущностей.
            self._rebuild_dto_caches()
            # DevTools #1 state-diff: record per-device deltas for this
            # polling refresh too.  Most of the time polling brings
            # no news when WS is alive, but during WS outages it's the
            # only signal the collector will see — keeping both paths
            # fed means DevTools stays accurate regardless.
            #
            # DevTools #4 command tracker: polling is also a valid way
            # to confirm outbound commands (especially while WS is down);
            # feed every device's reported_state into the tracker.
            try:
                for dev_id, dto in self.state_cache.get_all_devices().items():
                    reported_dicts = [a.to_dict() for a in dto.reported_state]
                    self.diff_collector.update(dev_id, reported_dicts, source="polling")
                    self.command_tracker.observe_reported_state(dev_id, reported_dicts)
                    self.validation_collector.observe_reported_state(dev_id, reported_dicts)
                # Close any commands that have been pending past the timeout.
                self.command_tracker.sweep()
            except Exception:  # pragma: no cover — defence in depth
                LOGGER.exception("DevTools hooks failed during polling")
            # Cleanup stale devices: если устройство пропало из Sber API
            # (user удалил его в приложении Sber или отвязал через panel),
            # удалим запись из device_registry — иначе на странице конфигурации
            # интеграции накапливаются "призраки".
            self._prune_stale_devices()
            # Sber scenarios + at_home — отдельный poll-cadence
            # (SCENARIO_POLL_INTERVAL_SEC), чтобы не нагружать API на
            # каждый device tick. Best-effort: ошибка не валит refresh.
            await self._maybe_poll_scenarios()
            await self._maybe_poll_ota()
            await self._maybe_poll_discovery()
            await self._maybe_poll_indicator()
            # Adaptive polling: когда WS connected, ослабляем polling до
            # 10 мин — WS уже шлёт real-time `reported_state` push'ами.
            # Tree polling нужен только для discovery новых устройств,
            # rename/group changes (WS их не покрывает) и safety net.
            # Когда WS offline — возвращаемся к user-интервалу (default 30 сек).
            desired_interval = self._desired_update_interval()
            if self.update_interval != desired_interval:
                self.update_interval = desired_interval
        except SberAuthError as err:
            self.error_count += 1
            LOGGER.warning("Authentication failed during update: %s", err)
            raise ConfigEntryAuthFailed(f"Authentication failed: {err}") from err
        except SberApiError as err:
            self.error_count += 1
            if err.retry_after:
                LOGGER.warning("Rate limited, retry after %ds: %s", err.retry_after, err)
                self.update_interval = timedelta(seconds=err.retry_after)
            raise UpdateFailed(f"API error: {err}") from err
        except (SberConnectionError, SberSmartHomeError) as err:
            self.error_count += 1
            LOGGER.warning("API communication error during update: %s", err)
            raise UpdateFailed(f"Error communicating with API: {err}") from err

        # WebSocket — additive: запускаем после первого успешного refresh,
        # чтобы AuthManager уже имел валидный companion-токен (handshake
        # реюзает его). При разрыве — auto-reconnect внутри WebSocketClient,
        # polling остаётся fallback'ом.
        #
        # Проверяем `.done()`, а не только `is None`: после
        # max_consecutive_failures WS task завершается, но объект task
        # остаётся в `_ws_task`. Без `.done()` условие не сработает и WS
        # больше никогда не рестартанёт — останется только polling.
        if self._ws_task is None or self._ws_task.done():
            self._start_ws_task()

        return self._derive_data()

    # ------------------------------------------------------------------
    # Sbermap entities cache — typed DeviceDto + HaEntityData
    # ------------------------------------------------------------------
    def _rebuild_dto_caches(self) -> None:
        """После polling refresh: reload StateCache из fresh tree + rebuild entities.

        ВАЖНО: вызывается ТОЛЬКО после `update_devices_cache()` — т.е. когда
        tree в `home_api.get_cached_tree()` свежий. Для optimistic-patch
        (после команды, до следующего polling) используется
        `_rebuild_entities_from_state_cache()` — он не трогает state_cache.
        """
        tree = self.home_api.get_cached_tree()
        if tree is not None:
            self.state_cache.update_from_tree(tree)
        else:
            # Fallback: tree не распарсился — заполним state_cache из raw DTO
            # через публичный метод (без лазания в `_devices` напрямую).
            self.state_cache.update_from_devices(self.home_api.get_cached_devices_dto())
        self._rebuild_entities_from_state_cache()

    def _rebuild_entities_from_state_cache(self) -> None:
        """Пересобрать `self.entities` из ТЕКУЩЕГО state_cache — БЕЗ перезаписи.

        Используется после optimistic `patch_device_desired` — state_cache
        уже содержит свежий desired_state, нам нужно только перемапить entities.
        Вызывать `_rebuild_dto_caches` в этом случае опасно: он перезаписывает
        state_cache из кэшированного tree (устаревшего), и optimistic patch
        теряется → UI flicker (ON → OFF → ON).
        """
        enabled = self.enabled_device_ids
        all_devices = self.state_cache.get_all_devices()
        if enabled is None:
            self.entities = {
                device_id: map_device_to_entities(dto) for device_id, dto in all_devices.items()
            }
        else:
            self.entities = {
                device_id: map_device_to_entities(dto)
                for device_id, dto in all_devices.items()
                if device_id in enabled
            }

    def _derive_data(self) -> dict[str, Any]:
        """Derive coordinator.data from state_cache (for HA framework compat).

        Returns dict[device_id → dto.to_dict()] filtered by enabled_device_ids.
        """
        all_devices = self.state_cache.get_all_devices()
        enabled = self.enabled_device_ids
        if enabled is not None:
            all_devices = {k: v for k, v in all_devices.items() if k in enabled}
        return {did: dto.to_dict() for did, dto in all_devices.items()}

    def _prune_stale_devices(self) -> None:
        """Удалить из device_registry устройства, пропавшие из Sber API.

        HA автоматически удалит привязанные entities вместе с DeviceEntry.
        Срабатывает при каждом успешном polling refresh. Stale-детектор:
        DeviceEntry привязан к нашему config_entry_id, но его identifier
        не встречается ни в `state_cache` (через serial_number / device_id),
        ни в `enabled_device_ids` (если они заданы — user-managed opt-in).

        Весь метод обёрнут в try/except — если в моках недоступен реальный
        DeviceRegistry, мы не валим весь coordinator refresh.
        """
        if self.config_entry is None:
            return
        try:
            from homeassistant.helpers import device_registry as dr

            device_reg = dr.async_get(self.hass)
            entry_id = self.config_entry.entry_id

            # Собираем identifiers (serial + device_id) из live state.
            live_identifiers: set[str] = set()
            enabled = self.enabled_device_ids
            for dev_id, dto in self.state_cache.get_all_devices().items():
                if enabled is not None and dev_id not in enabled:
                    continue
                if dto.serial_number:
                    live_identifiers.add(dto.serial_number)
                if dto.id:
                    live_identifiers.add(dto.id)
                live_identifiers.add(dev_id)

            stale: list[str] = []
            for device in dr.async_entries_for_config_entry(device_reg, entry_id):
                our_idents = {ident for (domain, ident) in device.identifiers if domain == DOMAIN}
                if not our_idents:
                    continue
                if our_idents.isdisjoint(live_identifiers):
                    stale.append(device.id)

            for dev_reg_id in stale:
                device_reg.async_remove_device(dev_reg_id)
                LOGGER.info("Pruned stale device %s from registry", dev_reg_id)
        except Exception:  # noqa: BLE001 — best-effort, не ломаем refresh
            LOGGER.debug("Stale device pruning failed (ignored)", exc_info=True)

    # ------------------------------------------------------------------
    # Sber scenarios + at_home variable
    # ------------------------------------------------------------------
    def _scenario_api(self) -> ScenarioAPI:
        """Shortcut к SberClient.scenarios."""
        return self.client.scenarios

    async def _maybe_poll_scenarios(self) -> None:
        """Throttled poll сценариев + at_home переменной.

        Не дёргает API чаще чем раз в SCENARIO_POLL_INTERVAL_SEC секунд.
        При первой ошибке ставит `_scenarios_disabled=True` — больше не
        пытаемся пока пользователь не сделает manual refresh (тогда
        флаг сбрасывается через `async_refresh_scenarios`).
        """
        if self._scenarios_disabled:
            return
        now = time.time()
        if (
            self._scenarios_last_poll_at is not None
            and now - self._scenarios_last_poll_at < SCENARIO_POLL_INTERVAL_SEC
        ):
            return
        try:
            await self._refresh_scenarios()
        except Exception:  # noqa: BLE001 — best-effort
            LOGGER.debug(
                "Scenario polling failed — disabling until manual refresh",
                exc_info=True,
            )
            self._scenarios_disabled = True
        finally:
            self._scenarios_last_poll_at = now

    async def _refresh_scenarios(self) -> None:
        api = self._scenario_api()
        scenarios = await api.list()
        try:
            at_home = await api.get_at_home()
        except Exception:  # noqa: BLE001 — at_home может быть не настроен у пользователя
            at_home = None
        self.scenarios = scenarios
        self.at_home = at_home

    async def async_refresh_scenarios(self) -> None:
        """Manual refresh из UI — сбрасывает _scenarios_disabled flag."""
        self._scenarios_disabled = False
        await self._refresh_scenarios()
        self._scenarios_last_poll_at = time.time()
        self.async_set_updated_data(self.data or {})

    async def async_execute_scenario(self, scenario_id: str) -> None:
        """Запустить Sber-сценарий по id (HA button.press)."""
        api = self._scenario_api()
        # Sber API: команда выполнения сценария — через `/command` с
        # body {"scenario_id": ...}. Точный shape варьируется; здесь
        # используем минимальный вариант, который наблюдается в обмене.
        await api.execute_command({"scenario_id": scenario_id})

    # ------------------------------------------------------------------
    # OTA polling
    # ------------------------------------------------------------------
    def _inventory_api(self) -> InventoryAPI:
        return self.client.inventory

    async def _maybe_poll_ota(self) -> None:
        if self._ota_disabled:
            return
        now = time.time()
        if (
            self._ota_last_poll_at is not None
            and now - self._ota_last_poll_at < OTA_POLL_INTERVAL_SEC
        ):
            return
        try:
            self.ota_upgrades = await self._inventory_api().list_ota_upgrades()
        except Exception:  # noqa: BLE001 — best-effort
            LOGGER.debug(
                "OTA polling failed — disabling until manual refresh",
                exc_info=True,
            )
            self._ota_disabled = True
        finally:
            self._ota_last_poll_at = now

    async def async_refresh_ota(self) -> None:
        """Manual refresh — UI button.

        Сбрасывает _ota_disabled и форсит свежий запрос.
        """
        self._ota_disabled = False
        self.ota_upgrades = await self._inventory_api().list_ota_upgrades()
        self._ota_last_poll_at = time.time()
        self.async_set_updated_data(self.data or {})

    # ------------------------------------------------------------------
    # Hub discovery polling
    # ------------------------------------------------------------------
    def _device_api(self) -> DeviceAPI:
        return self.client.devices

    def _hub_device_ids(self) -> list[str]:
        """Список device_id, для которых стоит дёргать /discovery.

        Отбирается по sbermap-resolve_category. Включает только
        категории из HUB_CATEGORIES.
        """
        from .sbermap import resolve_category

        result: list[str] = []
        for dev_id, dto in self.state_cache.get_all_devices().items():
            cat = resolve_category(dto.image_set_type)
            if cat in HUB_CATEGORIES:
                result.append(dev_id)
        return result

    async def _maybe_poll_discovery(self) -> None:
        if self._discover_disabled:
            return
        now = time.time()
        if (
            self._discover_last_poll_at is not None
            and now - self._discover_last_poll_at < DISCOVER_POLL_INTERVAL_SEC
        ):
            return
        api = self._device_api()
        new_info: dict[str, dict[str, Any]] = {}
        try:
            for dev_id in self._hub_device_ids():
                try:
                    info = await api.discover(dev_id)
                except Exception:  # noqa: BLE001
                    LOGGER.debug("Discovery failed for %s — skipping", dev_id, exc_info=True)
                    continue
                if isinstance(info, dict):
                    new_info[dev_id] = info
            self.discovery_info = new_info
        except Exception:  # noqa: BLE001 — defence in depth
            LOGGER.debug("Discovery polling outer failure", exc_info=True)
            self._discover_disabled = True
        finally:
            self._discover_last_poll_at = now

    # ------------------------------------------------------------------
    # Sber LED indicator polling
    # ------------------------------------------------------------------
    def _indicator_api(self) -> IndicatorAPI:
        return self.client.indicator

    async def _maybe_poll_indicator(self) -> None:
        if self._indicator_disabled:
            return
        now = time.time()
        if (
            self._indicator_last_poll_at is not None
            and now - self._indicator_last_poll_at < INDICATOR_POLL_INTERVAL_SEC
        ):
            return
        try:
            self.indicator_colors = await self._indicator_api().get()
        except Exception:  # noqa: BLE001
            LOGGER.debug(
                "Indicator polling failed — disabling until manual refresh",
                exc_info=True,
            )
            self._indicator_disabled = True
        finally:
            self._indicator_last_poll_at = now

    async def async_set_indicator_color(self, color: IndicatorColor) -> None:
        """Записать новый цвет индикатора + optimistic update."""
        await self._indicator_api().set(color)
        if self.indicator_colors is not None:
            new_current = list(self.indicator_colors.current_colors)
            # Заменяем по id если есть, иначе добавляем.
            replaced = False
            for idx, existing in enumerate(new_current):
                if existing.id == color.id:
                    new_current[idx] = color
                    replaced = True
                    break
            if not replaced:
                new_current.append(color)
            self.indicator_colors = IndicatorColors(
                default_colors=self.indicator_colors.default_colors,
                current_colors=new_current,
            )
        self.async_set_updated_data(self.data or {})

    async def async_set_at_home(self, value: bool) -> None:
        """Записать переменную at_home + optimistic update."""
        api = self._scenario_api()
        await api.set_at_home(value)
        # Optimistic — следующий poll подтвердит.
        self.at_home = value
        self.async_set_updated_data(self.data or {})

    def rebuild_caches_and_notify(self) -> None:
        """Публичный hook для entities после optimistic patch.

        Пересобирает `self.entities` из ТЕКУЩЕГО state_cache (с patched
        desired_state) и рассылает update подписчикам.

        **НЕ вызывает** `_rebuild_dto_caches` (который reload'ит state_cache
        из кэшированного tree) — это бы стёрло свежий optimistic patch и
        привело к UI flicker (ON → OFF → ON, яркость скачет). Fresh reload
        из tree происходит только в `_async_update_data` после реального
        polling refresh, когда tree уже обновлён.
        """
        self._rebuild_entities_from_state_cache()
        self.async_set_updated_data(self._derive_data())

    @property
    def enabled_device_ids(self) -> set[str] | None:
        """Set of device_ids выбранных пользователем, либо None если не настроено.

        Хранится в `config_entry.options["enabled_device_ids"]`. None означает
        "не настроено" (legacy/новая установка) → backward-compat passthrough.
        Пустой список означает "явно выбрано ничего" — opt-in 0 устройств.
        """
        if self.config_entry is None:
            return None
        if CONF_ENABLED_DEVICE_IDS not in self.config_entry.options:
            return None
        return set(self.config_entry.options[CONF_ENABLED_DEVICE_IDS])

    async def async_set_enabled_device_ids(self, device_ids: list[str]) -> None:
        """Persist enabled set в config_entry.options + убрать отвязанные
        устройства из device_registry, затем триггерить reload платформ.

        Раньше snимание галочки в панели оставляло "orphan device" (с
        потеряными entities) в Device registry HA — пользователь видел
        их бесконечно. Теперь вычисляем diff со старым set и удаляем
        устройства, которые были отвязаны.
        """
        from homeassistant.helpers import device_registry as dr

        previous = self.enabled_device_ids or set()
        new_set = set(device_ids)
        removed_ids = previous - new_set if previous else set()

        new_options = {
            **self.config_entry.options,
            CONF_ENABLED_DEVICE_IDS: list(device_ids),
        }

        # Обновляем snapshot ПЕРЕД update_entry, чтобы update_listener
        # (`_async_entry_updated`) увидел prev == current и пропустил
        # свой async-reload. Reload мы сделаем inline ниже и await'им —
        # так WS-caller дождётся завершения, и сразу после toggle_device
        # модалка увидит актуальное состояние (раньше между ответом WS и
        # завершением listener-reload был race → get_devices бросал
        # "Integration not loaded").
        self.hass.data[f"{DOMAIN}_options_{self.config_entry.entry_id}"] = dict(new_options)
        self.hass.config_entries.async_update_entry(self.config_entry, options=new_options)

        # Cleanup device_registry для отвязанных устройств. Удаление
        # записи DeviceEntry каскадно удаляет все entities — HA
        # делает это автоматически. DeviceInfo в entity.py использует
        # `serial_number OR device_id` как identifier, поэтому пробуем
        # оба варианта.
        if removed_ids:
            device_reg = dr.async_get(self.hass)
            for sber_device_id in removed_ids:
                dto = self.state_cache.get_device(sber_device_id)
                candidates: list[str] = []
                if dto is not None:
                    if dto.serial_number:
                        candidates.append(dto.serial_number)
                    if dto.id:
                        candidates.append(dto.id)
                candidates.append(sber_device_id)

                for ident in candidates:
                    device_entry = device_reg.async_get_device(identifiers={(DOMAIN, ident)})
                    if device_entry is not None:
                        device_reg.async_remove_device(device_entry.id)
                        LOGGER.info(
                            "Removed unlinked device %s (%s) from registry",
                            device_entry.name_by_user or device_entry.name,
                            sber_device_id,
                        )
                        break

        # Обновляем in-memory фильтр coordinator (до reload). Здесь
        # state_cache не трогаем — только entities фильтруются иначе.
        self._rebuild_entities_from_state_cache()
        self.async_set_updated_data(self._derive_data())

        # Inline reload — чтобы WS-caller (toggle_device) возвращался
        # уже с loaded-интеграцией, без race с update_listener'ом.
        await self.hass.config_entries.async_reload(self.config_entry.entry_id)

    # ------------------------------------------------------------------
    # WebSocket integration — real-time push updates
    # ------------------------------------------------------------------
    def _start_ws_task(self) -> None:
        """Запустить WebSocket subscription task в background."""
        try:
            self._ws_task = self.hass.async_create_background_task(
                self._run_ws(),
                name=f"{DOMAIN}_ws_subscriber",
            )
            LOGGER.debug("WebSocket subscription task scheduled")
        except Exception:  # pragma: no cover — defensive
            LOGGER.exception("Failed to schedule WS task — polling-only mode")

    async def _run_ws(self) -> None:
        """Создать WebSocketClient и крутить его infinite reconnect loop."""
        try:
            auth = await self.home_api.get_auth_manager()
        except Exception:
            LOGGER.exception("Cannot init AuthManager for WS — disabling WS push")
            return

        session = async_get_clientsession(self.hass)
        factory = make_aiohttp_factory(session)
        router = TopicRouter()
        # Первичные handlers — DTO-aware, делают patch state_cache / fire event.
        router.on(Topic.DEVICE_STATE, self._on_ws_device_state)
        router.on(Topic.DEVMAN_EVENT, self._on_ws_devman_event)
        router.on(Topic.GROUP_STATE, self._on_ws_group_state)
        # Phase 10: voice-intent dispatch — Sber пушит UPDATE_WIDGETS
        # каждый раз когда любой scenario срабатывает (включая голосовые).
        # Handler делает throttled fetch /scenario/v2/event и fire'ит
        # sberhome_intent HA event для каждого нового события.
        router.on(Topic.SCENARIO_WIDGETS, self._on_ws_scenario_widgets)
        # Всепоглощающий handler — логирует ВСЕ остальные topic'и, которые
        # не имеют специальной обработки (OTA, LAUNCHER_WIDGETS,
        # SCENARIO_HOME_CHANGE_VARIABLE, HOME_TRANSFER).
        # Пользователь видит их в панели, может скопировать JSON для
        # багрепорта, и мы не теряем новые типы сообщений с обновлением Sber API.
        for topic in Topic:
            if topic not in {
                Topic.DEVICE_STATE,
                Topic.DEVMAN_EVENT,
                Topic.GROUP_STATE,
                Topic.SCENARIO_WIDGETS,
            }:
                router.on(topic, self._on_ws_other_topic)

        self._ws_client = WebSocketClient(
            auth=auth,
            callback=router,
            factory=factory,
        )
        try:
            await self._ws_client.run()
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("WebSocket loop terminated unexpectedly")
        finally:
            # Сбрасываем клиент на None, чтобы `ws_connected` property не
            # показывал stale `is_connected` мёртвого клиента. Следующий
            # polling tick проверит `_ws_task.done()` и создаст новый.
            self._ws_client = None
            # Возвращаем короткий polling interval — WS offline, надо
            # опрашивать state чаще. Adaptive: 10 мин → 30 сек (default).
            # Триггерим immediate refresh чтобы не ждать следующего тика.
            self.update_interval = self._user_update_interval
            with contextlib.suppress(Exception):
                self.hass.async_create_task(self.async_request_refresh())

    def _record_ws_message(
        self,
        *,
        topic: str,
        device_id: str | None,
        payload: Any,
        direction: str = "in",
    ) -> None:
        """Append message в ring buffer + notify panel subscribers.

        Args:
            direction: "in" — входящее от Sber через WS, "out" — исходящая
                команда (HTTP PUT) от нас к Sber. Последнее — technically не
                WS, но полезно видеть в одном логе для корреляции.
        """
        record = {
            "ts": time.time(),
            "direction": direction,
            "topic": topic,
            "device_id": device_id,
            "payload": payload,
        }
        self._ws_log.append(record)
        self.last_ws_message_at = record["ts"]
        self.ws_message_count += 1
        for sub in list(self._ws_log_subscribers):
            try:
                sub(record)
            except Exception:  # noqa: BLE001 — best-effort fanout
                LOGGER.debug("WS log subscriber failed", exc_info=True)

    async def async_inject_ws_message(
        self,
        payload: dict[str, Any],
        *,
        mark_replay: bool = True,
    ) -> dict[str, Any]:
        """Feed a synthetic WS payload into the coordinator dispatch pipeline.

        Used by DevTools Replay / Inject: takes a raw ``SocketMessageDto``-shaped
        dict (exactly what the WS transport normally delivers) and runs it
        through the same handlers that real traffic hits —
        ``_on_ws_device_state`` / ``_on_ws_devman_event`` / ``_on_ws_group_state``
        / ``_on_ws_other_topic`` — without touching the broker.  Works offline;
        the state_cache, entities cache, state_diff collector and dispatcher
        signals all see the injected message indistinguishably from a real one
        (except for the ``direction="replay"`` marker in the WS message log,
        which the UI uses to tint synthetic rows).

        Args:
            payload: Raw SocketMessageDto-shaped dict (with exactly one of
                ``state`` / ``event`` / ``group_state`` / etc. populated).
            mark_replay: When True (default), the WS message log records
                ``direction="replay"`` instead of ``"in"`` so the UI can
                visually distinguish synthetic traffic.  Set False to make
                the injection indistinguishable from real WS traffic (e.g.
                reproducing a bug for a screenshot).

        Returns:
            Dict with ``{"topic": str, "handled": bool, "device_id": str|None}``.
            ``handled`` is False only when the payload has no recognisable
            topic (empty or malformed).
        """
        msg = SocketMessageDto.from_dict(payload)
        if msg is None:
            return {"topic": None, "handled": False, "device_id": None}
        topic = msg.topic
        device_id = msg.target_device_id

        # DevTools message log: tint synthetic rows differently.
        self._record_ws_message(
            topic=topic.value if topic else "INJECT",
            device_id=device_id,
            payload=payload,
            direction="replay" if mark_replay else "in",
        )

        if topic is None:
            return {"topic": None, "handled": False, "device_id": device_id}

        # Dispatch to the same handlers the real WS pipeline uses.  Kept
        # in sync with _run_ws() — adding a new handler there means adding
        # a case here too.
        if topic == Topic.DEVICE_STATE:
            await self._on_ws_device_state(msg)
        elif topic == Topic.DEVMAN_EVENT:
            await self._on_ws_devman_event(msg)
        elif topic == Topic.GROUP_STATE:
            await self._on_ws_group_state(msg)
        else:
            await self._on_ws_other_topic(msg)

        return {
            "topic": topic.value,
            "handled": True,
            "device_id": device_id,
        }

    def record_command(self, device_id: str, state: list[dict[str, Any]]) -> None:
        """Записать исходящую команду в ring buffer.

        Вызывается из `entity._async_send_attrs` после `set_device_state`,
        чтобы пользователь видел свои команды рядом с входящими push'ами
        (correlation debug: изменение состояния ↔ его источник).
        """
        self._record_ws_message(
            topic="COMMAND",
            device_id=device_id,
            payload={"desired_state": state},
            direction="out",
        )

    async def _on_ws_device_state(self, msg: SocketMessageDto) -> None:
        """Push DEVICE_STATE → точечный patch DTO + entities + notify (PR #11).

        Если в payload есть device_id — точечный patch через
        `sbermap.apply_reported_state` без HTTP. Если device_id отсутствует или
        устройство ещё не загружено — fallback на полный refresh.
        """
        if msg.state is None or not msg.state.reported_state:
            return

        device_id = msg.state.device_id or msg.target_device_id
        LOGGER.debug(
            "WS DEVICE_STATE for %s with %d attrs at %s",
            device_id or "<unknown>",
            len(msg.state.reported_state),
            msg.state.timestamp,
        )
        # Полный state.to_dict() в payload — user видит в панели все
        # attributes со значениями (не только keys) и может скопировать
        # JSON в багрепорт.
        self._record_ws_message(
            topic="DEVICE_STATE",
            device_id=device_id,
            payload=msg.state.to_dict() if msg.state else None,
        )

        # DevTools #1 state-diff: record the delta vs the previous push
        # for this device.  Empty deltas (identical-to-prior) are dropped
        # inside the collector.  Guard against any collector-side errors
        # so a DevTools bug can never break inbound state propagation.
        if device_id is not None:
            try:
                reported_dicts = [a.to_dict() for a in msg.state.reported_state]
                self.diff_collector.update(
                    device_id,
                    reported_dicts,
                    source="ws_push",
                    topic="DEVICE_STATE",
                )
                # DevTools #4 command tracker: close out any pending
                # outbound commands whose keys now match reported_state.
                self.command_tracker.observe_reported_state(device_id, reported_dicts)
                # DevTools #5 schema validator: flag unknown attr keys
                # or malformed type/value pairs in this snapshot.
                self.validation_collector.observe_reported_state(device_id, reported_dicts)
            except Exception:  # pragma: no cover — defence in depth
                LOGGER.exception("DevTools hooks failed for %s", device_id)

        if device_id is None or self.state_cache.get_device(device_id) is None:
            self.hass.async_create_task(self.async_request_refresh())
            return

        new_dto = self.state_cache.patch_device_state(device_id, msg.state.reported_state)
        if new_dto is not None:
            self.entities[device_id] = map_device_to_entities(new_dto)
        # Инкрементальный patch `coordinator.data` вместо `_derive_data()` —
        # последний пересоздаёт dict со всеми устройствами (O(N) на каждое
        # WS сообщение, и при сотнях устройств это заметная нагрузка на
        # каждый push). Тут мы точно знаем что изменилось — только этот
        # device_id.
        enabled = self.enabled_device_ids
        if enabled is None or device_id in enabled:
            patched_data: dict[str, Any] = dict(self.data) if self.data else {}
            if new_dto is not None:
                patched_data[device_id] = new_dto.to_dict()
            self.async_set_updated_data(patched_data)

    async def _on_ws_group_state(self, msg: SocketMessageDto) -> None:
        """GROUP_STATE → полный refresh для обновления tree/room mapping."""
        group_id = msg.target_device_id
        LOGGER.debug("WS GROUP_STATE for %s", group_id)
        self._record_ws_message(
            topic="GROUP_STATE",
            device_id=group_id,
            payload=msg.group_state.to_dict() if msg.group_state else None,
        )
        # Group changes can affect room↔device mapping — trigger full refresh.
        self.hass.async_create_task(self.async_request_refresh())

    async def _on_ws_scenario_widgets(self, msg: SocketMessageDto) -> None:
        """Phase 10: voice-intent dispatcher.

        Sber пушит ``scenario_widgets.UPDATE_WIDGETS`` каждый раз когда
        какой-либо сценарий срабатывает (включая голосовые), парами по
        ~100ms. Payload минимальный (`{"type": "UPDATE_WIDGETS"}`) — без
        scenario_id, нужно резолвить через event log.

        Алгоритм:
        1. Запись raw в panel ws_log (как и для остальных topic'ов).
        2. Через `asyncio.Lock` гарантируем что параллельные fetch'и не
           гоняются (duplicate WS push'ы порождают единственный fetch).
        3. ``GET /scenario/v2/event?home_id=X&limit=N`` — последние события.
        4. Фильтруем `event_time > self._last_intent_event_time`.
        5. На каждый новый — fire `EVENT_SBERHOME_INTENT` HA event с
           ``{name, scenario_id, event_time, type, account_id}``.
        6. Обновляем `last_intent_event_time` на самый свежий.
        """
        topic_name = msg.topic.value if msg.topic else "scenario_widgets"
        try:
            payload = msg.to_dict()
        except Exception:  # noqa: BLE001
            payload = {"error": "serialization_failed"}
        self._record_ws_message(
            topic=topic_name,
            device_id=msg.target_device_id,
            payload=payload,
        )

        # Best-effort: home_id из state_cache. Если его ещё нет
        # (первый refresh не прошёл) — skip dispatch, прилетит снова.
        home = self.state_cache.get_home()
        if home is None or not home.id:
            LOGGER.debug(
                "scenario_widgets push, but home_id not yet known — skipping intent dispatch"
            )
            return

        if self._intent_dispatch_lock.locked():
            # Дублирующий push (вторая половина пары) — fetch уже идёт.
            return

        async with self._intent_dispatch_lock:
            try:
                events = await self.client.scenarios.history(home.id, limit=INTENT_FETCH_LIMIT)
            except Exception:  # noqa: BLE001
                LOGGER.debug("Failed to fetch scenario history", exc_info=True)
                return

            new_events = self._select_new_intent_events(events)
            if not new_events:
                return

            for event in new_events:
                self._fire_intent_event(event)

            # Обновляем cursor на максимальный event_time, чтобы следующий
            # fetch не повторял эти же.
            latest = max(
                (e.event_time for e in new_events if e.event_time),
                default=self._last_intent_event_time,
            )
            self._last_intent_event_time = latest
            # Cooldown — guard от повторного fetch'а в follow-up push'е.
            await asyncio.sleep(INTENT_DISPATCH_COOLDOWN_SEC)

    def _select_new_intent_events(self, events: list[ScenarioEventDto]) -> list[ScenarioEventDto]:
        """Отфильтровать события, чьё ``event_time`` строго больше
        ранее обработанного cursor'а.

        Sber возвращает события отсортированными по `event_time desc`.
        При первом срабатывании (cursor=None) берём только самое свежее
        (limit=1) — иначе на старте integration'а fire'ится весь
        history.
        """
        if self._last_intent_event_time is None:
            # Первый запуск — берём только последнее, маркируем cursor.
            if not events:
                return []
            head = events[0]
            self._last_intent_event_time = head.event_time
            return [head]
        return [e for e in events if e.event_time and e.event_time > self._last_intent_event_time]

    def _fire_intent_event(self, event: ScenarioEventDto) -> None:
        """Fire ``EVENT_SBERHOME_INTENT`` в HA event bus.

        Payload готовится минимальным — только то, что нужно для
        автоматизации-trigger'а (`name`, `scenario_id`). Полные `data`
        и `meta` доступны но reduced — чтобы YAML-trigger был чистым.
        """
        data = {
            "name": (event.name or "").strip(),
            "scenario_id": event.object_id,
            "event_time": event.event_time,
            "type": event.type,
            "account_id": event.account_id,
        }
        LOGGER.debug("Firing %s with data=%s", EVENT_SBERHOME_INTENT, data)
        self.hass.bus.async_fire(EVENT_SBERHOME_INTENT, data)

    async def _on_ws_other_topic(self, msg: SocketMessageDto) -> None:
        """Логирование для topic'ов без специальной обработки.

        Покрывает INVENTORY_OTA, SCENARIO_HOME_CHANGE_VARIABLE,
        LAUNCHER_WIDGETS, HOME_TRANSFER. В панели пользователь видит, что
        эти события вообще приходят — для исследования Sber API поведения.
        """
        topic_name = msg.topic.value if msg.topic else "UNKNOWN"
        LOGGER.debug("WS %s received: %s", topic_name, msg)
        try:
            payload = msg.to_dict()
        except Exception:  # noqa: BLE001 — best-effort, не ломаем WS loop
            LOGGER.debug("WS %s: cannot serialize payload", topic_name, exc_info=True)
            payload = {"error": "serialization_failed"}
        self._record_ws_message(
            topic=topic_name,
            device_id=msg.target_device_id,
            payload=payload,
        )

    async def _on_ws_devman_event(self, msg: SocketMessageDto) -> None:
        """DEVMAN_EVENT — диспатч в HA через signal (PR #11).

        Event entities подписаны на SIGNAL_DEVMAN_EVENT и стреляют в HA event
        bus при получении (без ожидания polling).
        """
        device_id = msg.target_device_id
        LOGGER.debug("WS DEVMAN_EVENT for %s: %s", device_id, msg.event)
        if msg.event is None:
            return
        event_dict = msg.event.to_dict()
        self._record_ws_message(
            topic="DEVMAN_EVENT",
            device_id=device_id,
            payload=event_dict,
        )
        async_dispatcher_send(
            self.hass,
            SIGNAL_DEVMAN_EVENT,
            device_id,
            event_dict,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def async_shutdown(self) -> None:
        """Close API clients and stop WS task on shutdown."""
        await super().async_shutdown()
        if self._ws_client is not None:
            with contextlib.suppress(Exception):
                await self._ws_client.stop()
        if self._ws_task is not None:
            self._ws_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._ws_task
        # Home/Sber aclose no-op при DI (owns_http=False). Shared http
        # закрываем здесь — один раз, с contextlib на случай двойного вызова.
        await self.home_api.aclose()
        await self.sber_api.aclose()
        if self._shared_http is not None:
            with contextlib.suppress(RuntimeError):
                await self._shared_http.aclose()
            self._shared_http = None
