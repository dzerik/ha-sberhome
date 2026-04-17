"""The SberHome integration."""

from __future__ import annotations

import pathlib

from homeassistant.components.frontend import (
    async_register_built_in_panel,
    async_remove_panel,
)
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .api import HomeAPI, SberAPI, async_init_ssl
from .const import DOMAIN, LOGGER
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
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


async def async_setup_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> bool:
    """Set up SberHome from a config entry.

    Config flow завершается мгновенно после успешного OAuth — никакого
    blocking-вызова за device list. Coordinator поднимается «пустым»,
    первый refresh идёт background-task'ом, дальше поддерживается обычным
    polling timer'ом. Если token reaaly невалиден — обнаружится при первом
    poll'е и HA триггернет reauth (через `ConfigEntryAuthFailed`).

    Это даёт два эффекта:
    - Setup не висит на медленном/недоступном Sber API.
    - Никакой автоматический device-import при добавлении интеграции —
      пользователь идёт в панель и явно выбирает устройства (opt-in).
    """
    await async_init_ssl(hass)
    sber = SberAPI(token=entry.data["token"])
    home = HomeAPI(sber)

    coordinator = SberHomeCoordinator(hass, entry, sber, home)
    entry.runtime_data = coordinator

    # Panel + WS API всегда регистрируются — пользователь должен иметь
    # возможность открыть панель и выбрать устройства даже когда платформы
    # ещё не форварднуты (opt-in flow для новых установок).
    async_setup_websocket_api(hass)
    await _async_register_panel(hass)

    # Платформы форвардятся ТОЛЬКО если пользователь явно выбрал устройства
    # в панели. Новые установки стартуют с пустым enabled_device_ids → 0
    # entities в HA до выбора. Legacy установки (без ключа options) считаются
    # backward-compat passthrough — все устройства импортируются как раньше.
    if _should_forward_platforms(entry):
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Background-refresh — non-blocking. Panel сможет сразу показать список
    # как только Sber API ответит. Если ошибка — coordinator её залогирует
    # и retry на следующем polling cycle.
    hass.async_create_background_task(
        coordinator.async_refresh(),
        name=f"{DOMAIN}_initial_refresh",
    )

    # Update listener: при изменении options (e.g. enabled_device_ids через
    # panel) — релоадим entry, чтобы платформы появились/пересоздались.
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

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
    enabled = entry.options.get("enabled_device_ids")
    if enabled is None:
        return True
    return len(enabled) > 0


async def async_unload_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> bool:
    """Unload a config entry."""
    if _should_forward_platforms(entry):
        try:
            unloaded = await hass.config_entries.async_unload_platforms(
                entry, PLATFORMS
            )
        except ValueError:
            # Platforms were forwarded but not yet loaded (background refresh
            # hasn't completed). Safe to ignore — no entities to clean up.
            LOGGER.debug("Some platforms not loaded yet, skipping unload")
            unloaded = True
    else:
        unloaded = True
    # Если последняя SberHome-запись уходит — снимаем panel.
    if unloaded and not hass.config_entries.async_loaded_entries(DOMAIN):
        try:
            async_remove_panel(hass, _PANEL_URL_PATH)
        except Exception:  # noqa: BLE001 — best-effort
            LOGGER.debug("Panel %s already removed", _PANEL_URL_PATH)
    return unloaded


async def async_remove_entry(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> None:
    """Clean up when a config entry is removed."""
    from .auth_state import pending_auth_flows

    pending_auth_flows.pop(entry.entry_id, None)


async def _async_options_updated(
    hass: HomeAssistant, entry: SberHomeConfigEntry
) -> None:
    """Reload entry on options change (e.g. enabled_device_ids from panel).

    Reload пересоздаст coordinator и платформы — entities появятся/исчезнут
    в соответствии с новым enabled set.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_panel(hass: HomeAssistant) -> None:
    """Register frontend panel + static path (idempotent)."""
    marker = f"{DOMAIN}_panel_registered"
    if hass.data.get(marker):
        return

    panel_dir = str(pathlib.Path(__file__).parent / "www")
    await hass.http.async_register_static_paths(
        [StaticPathConfig(_PANEL_STATIC_PATH, panel_dir, cache_headers=False)]
    )

    from .const import VERSION  # avoid import cycle

    async_register_built_in_panel(
        hass,
        component_name="custom",
        sidebar_title="SberHome",
        sidebar_icon="mdi:home-assistant",
        frontend_url_path=_PANEL_URL_PATH,
        config={
            "_panel_custom": {
                "name": "sberhome-panel",
                "module_url": f"{_PANEL_STATIC_PATH}/sberhome-panel.js?v={VERSION}",
            }
        },
        require_admin=False,
    )
    hass.data[marker] = True


