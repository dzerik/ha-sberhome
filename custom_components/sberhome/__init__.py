"""The SberHome integration."""

from __future__ import annotations

import contextlib
import pathlib

import httpx
import voluptuous as vol
from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.loader import async_get_integration

from ._ha_token_store import HATokenStore
from .api import REQUEST_TIMEOUT, HomeAPI, SberAPI, async_init_ssl
from .const import CONF_ENABLED_DEVICE_IDS, CONF_TOKEN, DOMAIN, LOGGER
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .exceptions import SberSmartHomeError
from .websocket_api import async_setup_websocket_api

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.COVER,
    Platform.EVENT,
    Platform.FAN,
    Platform.HUMIDIFIER,
    Platform.LIGHT,
    Platform.MEDIA_PLAYER,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.VACUUM,
]

_PANEL_URL_PATH = "sberhome"
_PANEL_STATIC_PATH = "/sberhome_panel"


async def async_setup_entry(hass: HomeAssistant, entry: SberHomeConfigEntry) -> bool:
    """Set up SberHome from a config entry.

    Первый refresh выполняется через `async_config_entry_first_refresh` —
    платформы форвардятся только после того, как `coordinator.devices`
    заполнен, иначе `async_forward_entry_setups` создавал бы 0 entities.

    При ошибках refresh (`SberAuthError`/network/rate-limit) coordinator
    уже маппит их в `ConfigEntryAuthFailed` / `UpdateFailed`. HA-фреймворк
    из `UpdateFailed` первого refresh сам делает `ConfigEntryNotReady` и
    планирует retry. Дополнительно ловим голые SberSmartHomeError на
    случай ошибок до полноценного `_async_update_data`.
    """
    # Shared SSL + один httpx.AsyncClient на entry (оба API используют его
    # через DI). Без этого раньше создавались два независимых httpx клиента
    # с отдельными connection pool'ами и дубль SSL ручки.
    ssl_ctx = await async_init_ssl(hass)
    http = httpx.AsyncClient(verify=ssl_ctx, timeout=REQUEST_TIMEOUT)

    sber = SberAPI(token=entry.data[CONF_TOKEN], http=http)
    store = HATokenStore(hass, entry)
    # Ротированные SberID токены персистятся в entry.data, чтобы выживать
    # рестарт HA: refresh_token у Sber одноразовый, и без save_sberid
    # после первой ротации токен в entry.data становится невалиден.
    home = HomeAPI(
        sber,
        http=http,
        token_store=store,
        on_sberid_refreshed=store.save_sberid,
    )

    coordinator = SberHomeCoordinator(hass, entry, sber, home)
    # Shared http нужен coordinator.async_shutdown() чтобы закрыть его
    # один раз (aclose у sber/home теперь no-op при DI).
    coordinator._shared_http = http

    # Panel + WS API не зависят от devices — регистрируем до refresh,
    # чтобы при ConfigEntryNotReady (retry) панель и WS не перерегистрировались.
    async_setup_websocket_api(hass)
    await _async_register_panel(hass)

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        # Bubble up — HA запустит reauth flow. Клиент закрываем здесь,
        # так как coordinator.async_shutdown() не вызовется (entry не LOADED).
        await http.aclose()
        raise
    except SberSmartHomeError as err:
        # Сырые aiosber/Sber ошибки в обход coordinator mapping
        # (SberConnectionError/SberApiError тоже сюда попадают — они subclass'ы)
        # — превращаем в ConfigEntryNotReady для HA retry.
        await http.aclose()
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator

    # Платформы форвардятся ТОЛЬКО если пользователь явно выбрал устройства
    # в панели. Новые установки стартуют с пустым enabled_device_ids → 0
    # entities в HA до выбора. Legacy установки (без ключа options) считаются
    # backward-compat passthrough — все устройства импортируются как раньше.
    forwarded = _should_forward_platforms(entry)
    if forwarded:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Запоминаем факт форварда на случай reload'а: unload должен снимать
    # платформы только если они были подняты (иначе `async_unload_platforms`
    # бросает "Config entry was never loaded!"). На reload после
    # первого toggle enabled это и происходило — options уже изменились,
    # так что `_should_forward_platforms(entry)` возвращал True, хотя в
    # предыдущем setup платформы были пустыми и не форвардились.
    hass.data[f"{DOMAIN}_platforms_forwarded_{entry.entry_id}"] = forwarded

    # Reload на смену options из panel WS (enabled_device_ids).
    # Снэпшотим options, чтобы отличать update_entry(data=…) от
    # update_entry(options=…) — первое бывает часто (token rotation в
    # HATokenStore), и reload-каждый-раз привёл бы к перезапуску каждые
    # 24 часа без надобности.
    hass.data[f"{DOMAIN}_options_{entry.entry_id}"] = dict(entry.options)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    # Debug service для ручной отправки raw desired_state. Регистрируется
    # один раз (первый setup'ом) — idempotent через hass.data-маркер.
    _async_register_services(hass)

    return True


def _async_register_services(hass: HomeAssistant) -> None:
    """Регистрация debug service `sberhome.send_raw_command`.

    Позволяет из Developer Tools → Services отправить произвольный
    `desired_state` list в Sber API — для экспериментов с serialized format
    (напр. выяснить реальный диапазон saturation/brightness для конкретной
    лампы).

    Возвращает response: sent payload + device_id, так что видно что
    именно ушло. Реальный HTTP-response от Sber логируется на DEBUG
    уровне.
    """
    marker = f"{DOMAIN}_services_registered"
    if hass.data.get(marker):
        return

    schema = vol.Schema(
        {
            vol.Required("device_id"): str,
            vol.Required("state"): list,  # list[dict] — каждый dict AttributeValueDto JSON
        }
    )

    async def _send_raw(call: ServiceCall) -> dict[str, object]:
        device_id: str = call.data["device_id"]
        state: list[dict] = call.data["state"]

        # Находим любой loaded coordinator (обычно один entry).
        coord: SberHomeCoordinator | None = None
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            coord = entry.runtime_data
            break
        if coord is None:
            return {"ok": False, "error": "No loaded sberhome entry"}

        try:
            await coord.home_api.set_device_state(device_id, state)
        except Exception as err:  # noqa: BLE001 — debug service, нам нужен любой error в response
            LOGGER.warning(
                "send_raw_command to %s failed: %s (payload=%s)",
                device_id,
                err,
                state,
            )
            return {"ok": False, "error": str(err), "device_id": device_id, "state": state}

        LOGGER.info("send_raw_command to %s: %s", device_id, state)
        return {"ok": True, "device_id": device_id, "state": state}

    hass.services.async_register(
        DOMAIN,
        "send_raw_command",
        _send_raw,
        schema=schema,
        supports_response=SupportsResponse.OPTIONAL,
    )

    async def _refresh(call: ServiceCall) -> dict[str, object]:
        """Принудительно обновить state всех sberhome entries из Sber Gateway.

        Полезно когда WS push молчит или лаг / нужно гарантированно свежее
        значение перед автоматизацией. Возвращает число обновлённых entry.
        """
        refreshed = 0
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            coord: SberHomeCoordinator = entry.runtime_data
            await coord.async_request_refresh()
            refreshed += 1
        return {"ok": True, "refreshed_entries": refreshed}

    hass.services.async_register(
        DOMAIN,
        "refresh",
        _refresh,
        supports_response=SupportsResponse.OPTIONAL,
    )

    hass.data[marker] = True


async def _async_entry_updated(hass: HomeAssistant, entry: SberHomeConfigEntry) -> None:
    """React on options change only. data-only updates (token rotation) ignored.

    `OptionsFlowWithReload` не покрывает смену options через panel WS API
    (`coordinator.async_set_enabled_device_ids`), поэтому слушаем update_entry
    вручную. HA не даёт прямого сравнения "что именно изменилось", так что
    сохраняем snapshot в hass.data и сравниваем.
    """
    key = f"{DOMAIN}_options_{entry.entry_id}"
    prev = hass.data.get(key)
    current = dict(entry.options)
    if prev == current:
        return  # только data поменялось (токены) — не reloadим
    hass.data[key] = current
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: SberHomeConfigEntry) -> bool:
    """Миграция config entry между ConfigFlow VERSION.

    v1 → v2: legacy authlib-стиль `token["expires_at"]` конвертим в
    aiosber-стиль `token["obtained_at"]`. Раньше конвертация делалась
    на каждом чтении токена через `api._normalize_legacy_token` — это
    убирается после миграции, чтобы не тянуть compat-слой вечно.

    Downgrade guard: если entry.version > нашего handler'а, возвращаем
    False — HA покажет пользователю "Migration failed" вместо silent
    breakage. Это защищает от ситуации "HACS случайно откатил код на
    старую версию, а entry уже мигрирован в новую".
    """
    if entry.version > 2:
        LOGGER.error(
            "Cannot downgrade SberHome config entry from v%d to v2. "
            "Install a newer integration version or remove/re-add the entry.",
            entry.version,
        )
        return False

    if entry.version < 2:
        LOGGER.info(
            "Migrating SberHome config entry from v%d to v2",
            entry.version,
        )
        new_data = dict(entry.data)
        token = dict(new_data.get(CONF_TOKEN) or {})
        if "obtained_at" not in token and "expires_at" in token:
            expires_in = int(token.get("expires_in", 3600))
            token["obtained_at"] = token["expires_at"] - expires_in
            token.pop("expires_at", None)
            new_data[CONF_TOKEN] = token
        hass.config_entries.async_update_entry(entry, data=new_data, version=2)
        LOGGER.info("Migration to v2 complete")
    return True


def _should_forward_platforms(entry: SberHomeConfigEntry) -> bool:
    """Решить, надо ли форвардить platforms на основе opt-in выбора.

    - `enabled_device_ids` отсутствует в options → legacy install,
      passthrough (форвардим всегда).
    - `enabled_device_ids` пустой → opt-in новый install, ничего не
      форвардим, ждём выбора в панели.
    - `enabled_device_ids` непустой → форвардим, платформы создадут
      entities только для выбранных (фильтр в `coordinator._filter_enabled`).
    """
    enabled = entry.options.get(CONF_ENABLED_DEVICE_IDS)
    if enabled is None:
        return True
    return len(enabled) > 0


async def async_unload_entry(hass: HomeAssistant, entry: SberHomeConfigEntry) -> bool:
    """Unload a config entry.

    DataUpdateCoordinator.async_shutdown() вызывается HA-фреймворком только
    на `hass.stop`, НЕ на unload/reload. Поэтому явно вызываем его здесь,
    чтобы закрыть httpx клиенты и остановить WS task — иначе каждый reload
    интеграции оставлял бы живые connection pool'ы и background task'и.
    """
    # ВАЖНО: проверяем по snapshot факта форварда, а не по текущим
    # options — иначе после первого toggle enabled на реальной установке
    # (options изменились → `_should_forward_platforms` = True, но при
    # прошлом setup платформы не форвардились → `async_unload_platforms`
    # бросает "Config entry was never loaded!").
    was_forwarded = hass.data.pop(f"{DOMAIN}_platforms_forwarded_{entry.entry_id}", None)
    if was_forwarded is None:
        # Fallback для legacy setup'ов без флага (не должно срабатывать
        # после 3.8.1, но на всякий).
        was_forwarded = _should_forward_platforms(entry)
    if was_forwarded:
        unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    else:
        unloaded = True

    if unloaded:
        coordinator = entry.runtime_data
        if coordinator is not None:
            await coordinator.async_shutdown()

    # Если последняя SberHome-запись уходит — снимаем panel и очищаем
    # marker в hass.data, иначе повторное добавление integration не
    # зарегистрирует panel снова (ранний return в _async_register_panel).
    if unloaded and not hass.config_entries.async_loaded_entries(DOMAIN):
        with contextlib.suppress(KeyError, ValueError):
            async_remove_panel(hass, _PANEL_URL_PATH)
        hass.data.pop(f"{DOMAIN}_panel_registered", None)

    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: SberHomeConfigEntry) -> None:
    """Clean up when a config entry is removed."""
    from .auth_state import pending_auth_flows

    pending_auth_flows.pop(entry.entry_id, None)


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register frontend panel + static path (idempotent)."""
    marker = f"{DOMAIN}_panel_registered"
    if hass.data.get(marker):
        return

    panel_dir = str(pathlib.Path(__file__).parent / "www")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(_PANEL_STATIC_PATH, panel_dir, cache_headers=False)]
    )

    # Version читается из manifest.json через HA loader, чтобы cache-buster
    # panel JS менялся одновременно с версией интеграции (без дубля
    # константы в const.py, которая регулярно отставала от manifest).
    integration = await async_get_integration(hass, DOMAIN)
    version = integration.version or "0"

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="SberHome",
        sidebar_icon="mdi:home-assistant",
        frontend_url_path=_PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "sberhome-panel",
                "module_url": f"{_PANEL_STATIC_PATH}/sberhome-panel.js?v={version}",
            }
        },
        require_admin=False,
    )
    hass.data[marker] = True
