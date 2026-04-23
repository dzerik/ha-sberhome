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
from .aiosber import SocketMessageDto, StateCache, Topic, TopicRouter, WebSocketClient
from .aiosber.dto.device import DeviceDto
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
        # Всепоглощающий handler — логирует ВСЕ остальные topic'и, которые
        # не имеют специальной обработки (OTA, SCENARIO_WIDGETS,
        # LAUNCHER_WIDGETS, SCENARIO_HOME_CHANGE_VARIABLE, HOME_TRANSFER).
        # Пользователь видит их в панели, может скопировать JSON для
        # багрепорта, и мы не теряем новые типы сообщений с обновлением Sber API.
        for topic in Topic:
            if topic not in {Topic.DEVICE_STATE, Topic.DEVMAN_EVENT, Topic.GROUP_STATE}:
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

    async def _on_ws_other_topic(self, msg: SocketMessageDto) -> None:
        """Логирование для topic'ов без специальной обработки.

        Покрывает INVENTORY_OTA, SCENARIO_WIDGETS, SCENARIO_HOME_CHANGE_VARIABLE,
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
