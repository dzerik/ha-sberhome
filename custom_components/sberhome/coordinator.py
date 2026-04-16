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
from .aiosber import SocketMessageDto, Topic, TopicRouter, WebSocketClient
from .aiosber.dto.device import DeviceDto
from .api import HomeAPI, SberAPI
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, LOGGER
from .exceptions import (
    SberApiError,
    SberAuthError,
    SberConnectionError,
    SberSmartHomeError,
)
from .sbermap import (
    HaEntityData,
    apply_reported_state,
    device_dto_to_entities,
)

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
        scan_interval = entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )
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
        # Параллельные кэши на DTO/sbermap (заполняются после каждого refresh).
        # `data` остаётся legacy dict для обратной совместимости с платформами,
        # которые ещё не мигрированы. PR #3-#7 переведут платформы на эти каналы;
        # PR #8 удалит `data`.
        self.devices: dict[str, DeviceDto] = {}
        self.entities: dict[str, list[HaEntityData]] = {}
        # Stats для panel (PR #12) — count + last timestamps + ring buffer WS msgs.
        self.last_polling_at: float | None = None
        self.last_ws_message_at: float | None = None
        self.polling_count: int = 0
        self.error_count: int = 0
        self.ws_message_count: int = 0
        self._ws_log: deque[dict[str, Any]] = deque(maxlen=100)
        self._ws_log_subscribers: list[Callable[[dict[str, Any]], None]] = []

    async def _async_setup(self) -> None:
        """Perform initial setup on first coordinator refresh."""
        LOGGER.debug("Coordinator initial setup complete")

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the SberHome API."""
        try:
            await self.home_api.update_devices_cache()
            devices = self.home_api.get_cached_devices()
            LOGGER.debug("Updated %d devices from API", len(devices))
            self.last_polling_at = time.time()
            self.polling_count += 1
            # Параллельно строим типизированные DTO + кэш sbermap-сущностей.
            self._rebuild_dto_caches()
            # Восстанавливаем пользовательский интервал после успешного опроса
            # (мог быть понижен до retry_after при 429).
            if self.update_interval != self._user_update_interval:
                self.update_interval = self._user_update_interval
        except SberAuthError as err:
            self.error_count += 1
            LOGGER.warning("Authentication failed during update: %s", err)
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except SberApiError as err:
            self.error_count += 1
            if err.retry_after:
                LOGGER.warning(
                    "Rate limited, retry after %ds: %s", err.retry_after, err
                )
                self.update_interval = timedelta(seconds=err.retry_after)
            raise UpdateFailed(
                f"API error: {err}"
            ) from err
        except (SberConnectionError, SberSmartHomeError) as err:
            self.error_count += 1
            LOGGER.warning("API communication error during update: %s", err)
            raise UpdateFailed(
                f"Error communicating with API: {err}"
            ) from err

        # После первого успешного polling запускаем WS-task для real-time updates.
        if self._ws_task is None:
            self._start_ws_task()
        return devices

    # ------------------------------------------------------------------
    # Sbermap entities cache — typed DeviceDto + HaEntityData
    # ------------------------------------------------------------------
    def _rebuild_dto_caches(self) -> None:
        """Перестроить `self.devices` и `self.entities` из cached raw dicts.

        `self.devices` содержит **все** Sber-устройства (для panel device picker).
        `self.entities` строится с фильтром через `enabled_device_ids` (PR #12):
        - Если ключ отсутствует в options (legacy installs ≤ v2.3.0 или новая
          установка ещё не настроенная) → entities для ВСЕХ devices
          (backward-compat).
        - Если список присутствует (даже пустой — opt-in) → entities только
          для выбранных. Disabled devices → нет entities → HA пометит unavailable.
        """
        self.devices = self.home_api.get_cached_devices_dto()
        enabled = self.enabled_device_ids
        if enabled is None:
            # Legacy / not configured yet — pass through all devices.
            self.entities = {
                device_id: device_dto_to_entities(dto)
                for device_id, dto in self.devices.items()
            }
        else:
            self.entities = {
                device_id: device_dto_to_entities(dto)
                for device_id, dto in self.devices.items()
                if device_id in enabled
            }

    @property
    def enabled_device_ids(self) -> set[str] | None:
        """Set of device_ids выбранных пользователем, либо None если не настроено.

        Хранится в `config_entry.options["enabled_device_ids"]`. None означает
        "не настроено" (legacy/новая установка) → backward-compat passthrough.
        Пустой список означает "явно выбрано ничего" — opt-in 0 устройств.
        """
        if self.config_entry is None:
            return None
        if "enabled_device_ids" not in self.config_entry.options:
            return None
        return set(self.config_entry.options["enabled_device_ids"])

    async def async_set_enabled_device_ids(self, device_ids: list[str]) -> None:
        """Persist enabled set в config_entry.options + перестроить entities.

        Триггерит reload платформ через update_listener в `__init__.py`.
        """
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            options={
                **self.config_entry.options,
                "enabled_device_ids": list(device_ids),
            },
        )
        self._rebuild_dto_caches()
        self.async_set_updated_data(self.home_api.get_cached_devices())

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
        router.on(Topic.DEVICE_STATE, self._on_ws_device_state)
        router.on(Topic.DEVMAN_EVENT, self._on_ws_devman_event)

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

    def _record_ws_message(
        self, *, topic: str, device_id: str | None, payload: Any
    ) -> None:
        """Append WS message в ring buffer + notify panel subscribers."""
        record = {
            "ts": time.time(),
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

    async def _on_ws_device_state(self, msg: SocketMessageDto) -> None:
        """Push DEVICE_STATE → точечный patch DTO + entities + notify (PR #11).

        Если в payload есть device_id — точечный patch через
        `sbermap.apply_reported_state` без HTTP. Если device_id отсутствует или
        устройство ещё не загружено — fallback на полный refresh.
        """
        if msg.state is None or not msg.state.reported_state:
            return

        device_id = msg.target_device_id
        LOGGER.debug(
            "WS DEVICE_STATE for %s with %d attrs at %s",
            device_id or "<unknown>",
            len(msg.state.reported_state),
            msg.state.timestamp,
        )
        self._record_ws_message(
            topic="DEVICE_STATE",
            device_id=device_id,
            payload={
                "attrs": [av.key for av in msg.state.reported_state],
                "timestamp": msg.state.timestamp,
            },
        )

        if device_id is None or device_id not in self.devices:
            self.hass.async_create_task(self.async_request_refresh())
            return

        old_dto = self.devices[device_id]
        new_dto = apply_reported_state(old_dto, msg.state.reported_state)
        self.devices[device_id] = new_dto
        self.entities[device_id] = device_dto_to_entities(new_dto)
        self.home_api._cached_devices[device_id] = new_dto.to_dict()
        self.async_set_updated_data(self.home_api.get_cached_devices())

    async def _on_ws_devman_event(self, msg: SocketMessageDto) -> None:
        """DEVMAN_EVENT — диспатч в HA через signal (PR #11).

        Event entities подписаны на SIGNAL_DEVMAN_EVENT и стреляют в HA event
        bus при получении (без ожидания polling).
        """
        device_id = msg.target_device_id
        LOGGER.debug("WS DEVMAN_EVENT for %s: %s", device_id, msg.event)
        if msg.event is None:
            return
        self._record_ws_message(
            topic="DEVMAN_EVENT",
            device_id=device_id,
            payload=msg.event,
        )
        async_dispatcher_send(
            self.hass,
            SIGNAL_DEVMAN_EVENT,
            device_id,
            msg.event,
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
        await self.home_api.aclose()
        await self.sber_api.aclose()
