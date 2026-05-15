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

from ._ha_token_store import HACsafrontTokenStore, HATokenStore
from .aiosber.auth import (
    AuthManager,
    AuthManagerProtocol,
    CsafrontAuthManager,
    CsafrontTokens,
)
from .aiosber.const import AUTH_METHOD_CSAFRONT, AUTH_METHOD_SBERID
from .aiosber.transport import HttpTransport
from .api import REQUEST_TIMEOUT, SberAPI, async_init_ssl
from .conflict import ISSUE_ID as CONFLICT_ISSUE_ID
from .conflict import async_update_conflict_issue
from .const import CONF_AUTH_METHOD, CONF_ENABLED_DEVICE_IDS, CONF_TOKEN, DOMAIN, LOGGER
from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
from .exceptions import SberSmartHomeError
from .intents.reconciler import reconcile_intents
from .intents.service import IntentService
from .intents.yaml_loader import INTENTS_SCHEMA, load_intents_from_config
from .listeners import LISTENERS_SCHEMA, load_listeners_from_config
from .websocket_api import async_setup_websocket_api

# YAML-config для voice intents — опциональная декларативная альтернатива
# UI-вкладке «Voice Intents». См. intents/yaml_loader.py для shape.
CONF_INTENTS = "intents"
# YAML-config для read-only listeners (Sber scenario events → HA events).
# См. listeners/yaml_loader.py для shape.
CONF_LISTENERS = "listeners"

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_INTENTS, default=[]): INTENTS_SCHEMA,
                vol.Optional(CONF_LISTENERS, default=[]): LISTENERS_SCHEMA,
            }
        ),
    },
    extra=vol.ALLOW_EXTRA,
)

# Ключ в hass.data для хранения распарсенных YAML intent'ов между
# `async_setup()` (где config доступен) и `async_setup_entry()` /
# service reload (где доступа к config-arg нет).
_HASS_DATA_YAML_INTENTS = f"{DOMAIN}_yaml_intents"
# Аналогичный ключ для listeners — раздаётся между async_setup и
# async_setup_entry где coordinator + state_cache уже готовы для резолва
# `filter.home` (по имени) → home_id (UUID).
_HASS_DATA_YAML_LISTENERS = f"{DOMAIN}_yaml_listeners"

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
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
    Platform.VACUUM,
]

_PANEL_URL_PATH = "sberhome"
_PANEL_STATIC_PATH = "/sberhome_panel"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """YAML-секция `sberhome:` — парсим и кэшируем для reconcile.

    Вызывается HA до setup_entry. Если в `configuration.yaml` есть
    блок `sberhome.intents:`, парсим его в `IntentSpec`-ы и сохраняем
    в `hass.data` для последующей применения через reconcile_intents().

    Парсинг — fail-soft: ошибка в YAML логируется, но не блокирует
    setup интеграции (config_entry-flow всё ещё работает).
    """
    domain_config = config.get(DOMAIN) or {}
    raw_intents = domain_config.get(CONF_INTENTS) or []
    intent_specs: list = []
    if raw_intents:
        try:
            intent_specs = load_intents_from_config(raw_intents)
        except (vol.Invalid, ValueError) as err:
            LOGGER.error(
                "Ошибка в configuration.yaml sberhome.intents: %s. "
                "YAML-intents игнорируются до исправления.",
                err,
            )
            intent_specs = []
        else:
            LOGGER.info(
                "YAML sberhome.intents: загружено %d intent(s) — будут "
                "синхронизированы с Sber после первого refresh.",
                len(intent_specs),
            )
    hass.data[_HASS_DATA_YAML_INTENTS] = intent_specs

    # Listeners: парсим в том же async_setup. Slugs intents считаем
    # «зарезервированными» — listener с тем же slug автоматически
    # будет отключён (см. listeners.yaml_loader).
    raw_listeners = domain_config.get(CONF_LISTENERS) or []
    listener_specs: list = []
    if raw_listeners:
        reserved_slugs = {
            s.raw_extras.get("yaml_slug") for s in intent_specs if s.raw_extras.get("yaml_slug")
        }
        try:
            listener_specs = load_listeners_from_config(
                raw_listeners, reserved_slugs=reserved_slugs
            )
        except (vol.Invalid, ValueError) as err:
            LOGGER.error(
                "Ошибка в configuration.yaml sberhome.listeners: %s. "
                "YAML-listeners игнорируются до исправления.",
                err,
            )
            listener_specs = []
        else:
            LOGGER.info(
                "YAML sberhome.listeners: загружено %d listener(s) — "
                "будут активированы после первого refresh (home_id резолв).",
                len(listener_specs),
            )
    hass.data[_HASS_DATA_YAML_LISTENERS] = listener_specs

    return True


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
    # Shared SSL + один httpx.AsyncClient на entry (используется SberAPI и
    # HttpTransport через DI). Без этого раньше создавались два независимых
    # httpx клиента с отдельными connection pool'ами и дубль SSL ручки.
    ssl_ctx = await async_init_ssl(hass)
    http = httpx.AsyncClient(verify=ssl_ctx, timeout=REQUEST_TIMEOUT)

    # SberAPI инстанс нужен для config_flow PKCE-обновления (reauth) и
    # для legacy SberID flow. Для CSAFront flow SberID-токенов нет —
    # передаём пустой dict.
    sber_token = entry.data.get(CONF_TOKEN) or {"access_token": ""}
    sber = SberAPI(token=sber_token, http=http)

    # Диспатч на нужный auth manager по auth_method (default — legacy SberID).
    auth_method = entry.data.get(CONF_AUTH_METHOD, AUTH_METHOD_SBERID)
    auth: AuthManagerProtocol
    if auth_method == AUTH_METHOD_CSAFRONT:
        csaf_store = HACsafrontTokenStore(hass, entry)
        csaf_data = entry.data.get("csafront_tokens")
        if not csaf_data:
            await http.aclose()
            raise ConfigEntryAuthFailed("CSAFront tokens missing — reauth required")
        initial = CsafrontTokens.from_dict(csaf_data)
        auth = CsafrontAuthManager(
            http=http,
            store=csaf_store,
            initial=initial,
            on_tokens_refreshed=csaf_store.save_refreshed,
        )
    else:
        store = HATokenStore(hass, entry)
        # Ротированные SberID токены персистятся в entry.data, чтобы выживать
        # рестарт HA: refresh_token у Sber одноразовый, и без save_sberid
        # после первой ротации токен в entry.data становится невалиден.
        auth = AuthManager(
            http=http,
            store=store,
            sberid_tokens=sber.sberid_tokens,
            on_sberid_refreshed=store.save_sberid,
        )
    transport = HttpTransport(http=http, auth=auth)

    coordinator = SberHomeCoordinator(hass, entry, sber, transport, auth)
    # Shared http нужен coordinator.async_shutdown() чтобы закрыть его
    # один раз (aclose у sber теперь no-op при DI, transport не владеет http).
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

    # YAML-driven intents reconcile — best-effort, не блокирует setup
    # при ошибке. Применяется после первого успешного refresh, чтобы
    # state_cache.get_homes() уже знал все дома (нужен intent service
    # для populate last_fired_at).
    await _async_reconcile_yaml_intents(hass, coordinator)

    # YAML-driven listeners — резолв filter.home (по имени) → home_id
    # выполняется после первого refresh, когда state_cache знает дома.
    _async_apply_yaml_listeners(hass, coordinator)

    # Детектор конфликта с альтернативными Sber-интеграциями (issue #10).
    async_update_conflict_issue(hass)

    return True


async def _async_reconcile_yaml_intents(
    hass: HomeAssistant, coordinator: SberHomeCoordinator
) -> None:
    """Применить кэшированные в hass.data YAML-intents к Sber.

    Best-effort: ошибка не блокирует setup интеграции. Подробный отчёт
    о create/update/orphan/failed уходит в LOGGER.info / warning.
    """
    yaml_specs = hass.data.get(_HASS_DATA_YAML_INTENTS) or []
    if not yaml_specs:
        return
    try:
        service = IntentService(coordinator)
        homes = coordinator.state_cache.get_homes()
        report = await reconcile_intents(service, yaml_specs, homes=homes)
        LOGGER.info("YAML intents reconciled: %s", report.summary_line())
    except Exception:  # noqa: BLE001 — best-effort
        LOGGER.exception(
            "YAML intents reconcile failed — продолжаем без них. "
            "После исправления вызовите service `sberhome.reload_intents`."
        )


def _async_apply_yaml_listeners(hass: HomeAssistant, coordinator: SberHomeCoordinator) -> None:
    """Подключить YAML-listeners к coordinator.listener_registry.

    Резолв filter.home: если в YAML был ``home`` (имя), ищем UUID
    среди реальных домов из state_cache. Если не нашли — listener
    отключается (enabled=False) с warning в лог. Если в YAML был
    ``home_id`` и он уже UUID реального дома — пропускаем как есть.

    Идемпотентно: ``listener_registry.replace(...)`` полностью
    заменяет содержимое реестра.
    """
    from dataclasses import replace

    yaml_listeners = hass.data.get(_HASS_DATA_YAML_LISTENERS) or []
    if not yaml_listeners:
        # Явно очищаем registry — могло остаться от прошлого reload'а.
        coordinator.listener_registry.replace([])
        return

    homes = coordinator.state_cache.get_homes()
    homes_by_id = {h.id for h in homes}
    homes_by_name = {h.name.strip().casefold(): h.id for h in homes if h.name}

    resolved_specs = []
    for spec in yaml_listeners:
        raw_home = spec.filter.home_id
        if raw_home is None:
            resolved_specs.append(spec)
            continue
        if raw_home in homes_by_id:
            # Уже UUID реального дома — оставляем как есть.
            resolved_specs.append(spec)
            continue
        resolved_home_id = homes_by_name.get(raw_home.strip().casefold())
        if resolved_home_id is None:
            LOGGER.warning(
                "Listener %r filter.home=%r не найден среди реальных домов — disabled",
                spec.name,
                raw_home,
            )
            resolved_specs.append(replace(spec, enabled=False))
            continue
        new_filter = replace(spec.filter, home_id=resolved_home_id)
        new_spec = replace(spec, filter=new_filter)
        resolved_specs.append(new_spec)

    coordinator.listener_registry.replace(resolved_specs)
    LOGGER.info(
        "YAML listeners применены: %d (enabled=%d) к coordinator.listener_registry",
        len(resolved_specs),
        sum(1 for s in resolved_specs if s.enabled),
    )


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
        from datetime import UTC, datetime

        device_id: str = call.data["device_id"]
        state: list[dict] = call.data["state"]

        # Находим любой loaded coordinator (обычно один entry).
        coord: SberHomeCoordinator | None = None
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            coord = entry.runtime_data
            break
        if coord is None:
            return {"ok": False, "error": "No loaded sberhome entry"}

        # Debug service: пишем raw через transport — без AttributeValueDto
        # парсинга, чтобы пользователь мог отправить даже некорректные
        # payloads и увидеть как gateway отреагирует.
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        try:
            await coord.client.transport.put(
                f"/devices/{device_id}/state",
                json={
                    "device_id": device_id,
                    "desired_state": state,
                    "timestamp": timestamp,
                },
            )
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

    async def _reload_intents(call: ServiceCall) -> dict[str, object]:
        """Перечитать `configuration.yaml:sberhome.intents` + reconcile.

        Не требует рестарта HA — удобно после правки YAML.
        Возвращает отчёт ReconcileReport.to_dict() для каждого
        loaded entry. Additive: orphan'ы только логируются, не
        удаляются.
        """
        from homeassistant.config import load_yaml_config_file

        try:
            # HA helper: возвращает уже распарсенный configuration.yaml.
            yaml_path = hass.config.path("configuration.yaml")
            yaml_config = await hass.async_add_executor_job(load_yaml_config_file, yaml_path)
        except (FileNotFoundError, OSError) as err:
            return {"ok": False, "error": f"YAML недоступен: {err}"}
        except Exception as err:  # noqa: BLE001 — yaml parse error etc.
            return {"ok": False, "error": f"YAML parse failed: {err}"}

        # Валидируем через CONFIG_SCHEMA
        try:
            validated = CONFIG_SCHEMA({DOMAIN: yaml_config.get(DOMAIN) or {}})
        except vol.Invalid as err:
            return {"ok": False, "error": f"YAML schema invalid: {err}"}

        raw_intents = validated[DOMAIN].get(CONF_INTENTS) or []
        try:
            specs = load_intents_from_config(raw_intents)
        except (vol.Invalid, ValueError) as err:
            return {"ok": False, "error": str(err)}

        hass.data[_HASS_DATA_YAML_INTENTS] = specs

        # Listeners (v5.5.0+) перечитываем в той же service-команде.
        # Cross-collection slug collision: intents reserved первыми.
        raw_listeners = validated[DOMAIN].get(CONF_LISTENERS) or []
        try:
            reserved_slugs = {
                s.raw_extras.get("yaml_slug") for s in specs if s.raw_extras.get("yaml_slug")
            }
            listener_specs = load_listeners_from_config(
                raw_listeners, reserved_slugs=reserved_slugs
            )
        except (vol.Invalid, ValueError) as err:
            return {"ok": False, "error": f"listeners: {err}"}
        hass.data[_HASS_DATA_YAML_LISTENERS] = listener_specs

        # Применяем ко всем loaded entry — обычно один.
        results: dict[str, object] = {}
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            coord: SberHomeCoordinator | None = entry.runtime_data
            if coord is None:
                continue
            service = IntentService(coord)
            try:
                homes = coord.state_cache.get_homes()
                report = await reconcile_intents(service, specs, homes=homes)
                results[entry.entry_id] = report.to_dict()
            except Exception as err:  # noqa: BLE001
                LOGGER.exception("reload_intents reconcile failed")
                results[entry.entry_id] = {"error": str(err)}
            # Listeners применяются отдельно от reconcile — home_id резолв
            # из state_cache + replace в coordinator.listener_registry.
            try:
                _async_apply_yaml_listeners(hass, coord)
            except Exception:  # noqa: BLE001
                LOGGER.exception("reload_intents: listeners apply failed")

        LOGGER.info(
            "Service sberhome.reload_intents: %d intent(s) + %d listener(s) "
            "processed across %d entry(ies)",
            len(specs),
            len(listener_specs),
            len(results),
        )
        return {
            "ok": True,
            "intents_count": len(specs),
            "listeners_count": len(listener_specs),
            "results": results,
        }

    hass.services.async_register(
        DOMAIN,
        "reload_intents",
        _reload_intents,
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
        # Последняя запись ушла — снимаем repair issue о конфликте.
        from homeassistant.helpers import issue_registry as ir

        ir.async_delete_issue(hass, DOMAIN, CONFLICT_ISSUE_ID)

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
