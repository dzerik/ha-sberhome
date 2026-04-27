# Changelog

## [4.0.0] — 2026-04-27

Major release: расширение API-coverage и новые HA-сущности поверх ранее
реализованных, но неиспользуемых aiosber-доменов. 9 фаз в одном бранче,
104 новых теста (872 → 976), все зелёные.

### Added

- **Sber Cloud Scenarios → HA buttons**. Каждый сценарий из мобильного
  приложения «Салют!» появляется как button в virtual-устройстве
  «Sber Scenarios». Press → `ScenarioAPI.execute_command(scenario_id)`.
- **At-home presence**:
  - `binary_sensor.sber_at_home` (presence device class) зеркалит
    глобальную переменную `at_home` из Sber-облака.
  - `switch.sber_at_home` пишет обратно через `ScenarioAPI.set_at_home`
    с optimistic update.
- **Sber LED indicator light**: `light.sber_indicator_color` (HSV)
  управляет цветом и яркостью кольца на колонках через `IndicatorAPI`.
- **Per-device firmware updates**: `update.<device>_firmware` per
  устройству (registry-disabled by default, включается вручную).
  Источник — `/inventory/ota-upgrades` через новый `InventoryAPI`.
- **Hub sub-device counter**: `sensor.<hub>_subdevice_count` для
  SberBoom Home / SberPortal / intercom. Источник —
  `/devices/{id}/discovery`.
- **Sber-speaker категория** (`dt_boom_*` / `dt_portal_*` / `dt_box_*`
  / `dt_satellite_*`): primary connectivity binary sensor + diagnostic
  `zigbee_ready`/`matter_ready`/`staros_has_hub`/`sub_pairing`/`detector`
  + `select.position`. Раньше эти устройства попадали в «не
  поддерживается».
- **`scenario_button` / cat_button_m**: виртуальные c2c-кнопки типа
  «Эмуляция присутствия» теперь распознаются и создают `event` entity
  с `click`/`double_click`/`long_press`.
- **`select.options` fallback** через `/devices/enums` cache: если
  Sber вернул ENUM-атрибут без enum_values inline, options
  подтягиваются из закешированного справочника. Чинит «голые»
  dropdowns у некоторых c2c-устройств.
- **3 новых aiosber API-домена**:
  - `InventoryAPI` — `/inventory/{ota-upgrades,tokens,otp}`.
  - `LightEffectsAPI` — `/light/effects`.
  - `ScenarioTemplatesAPI` — `/scenario-templates/*`.
- **8 новых WS-эндпоинтов для panel/custom cards**:
  - `sberhome/rename_room` — GroupAPI.rename + force tree refresh.
  - `sberhome/refresh_scenarios` — manual reset `_scenarios_disabled`.
  - `sberhome/refresh_ota` — manual reset `_ota_disabled`.
  - `sberhome/pairing/wifi_credentials` — bootstrap SSID + temp pwd.
  - `sberhome/pairing/matter_categories` — каталог Matter.
  - `sberhome/pairing/start` — `POST /devices/pairing`.
  - `sberhome/pairing/matter_{attestation,noc,complete,
    connect_controller,connect_device}` — Matter handshake chain.

### Changed

- **`coordinator.client`** — публичный SberClient facade lazy-built
  поверх `home_api._transport`. Закрывает архитектурный долг (CLAUDE.md,
  парадигма пункт 6: «один публичный фасад SberClient»). Все internal
  API-factories (`_scenario_api`, `_inventory_api`, `_device_api`,
  `_indicator_api`) и WS-эндпоинты (rooms, pairing) теперь делегируют
  через `coordinator.client.<domain>`.
- **Multi-cadence background polling**: scenarios каждые 5 минут,
  OTA / discovery / indicator каждый час. Best-effort: ошибка в одном
  потоке не валит остальные, выставляет `_*_disabled` flag и снимает
  его после manual refresh.
- **`scenario_button` event_types**: добавлен `long_press` (был
  только `click`/`double_click`, реальные устройства отдают и третий).
- **UI panel**: устройства с unknown category показываются с бейджем
  «не поддерживается» (оранжевый), включить нельзя (server-side
  guard в `ws_toggle_device` + `ws_set_enabled`).

### Architecture

- **15 HA-платформ** (было 14): добавлен `Platform.UPDATE`.
- **8 aiosber API-доменов** (было 5): + Inventory, LightEffects,
  ScenarioTemplates.
- **976 тестов** (было 872): +104 unit + integration.

## [3.14.7] — 2026-04-24

### Fixed

- **Panel: `css is not a function` в чистых HA-установках**.  Раньше
  компоненты получали `LitElement`, `html`, `css` через
  `Object.getPrototypeOf(customElements.get("ha-panel-lovelace"))` —
  этот подход зависит от того, гидратируют ли `html`/`css` через
  prototype сторонние HACS-карты.  В «толстых» установках панель
  работала, в «чистых» — падала при первом рендере.

### Changed

- **Vendored lit 3.2.1** — `www/vendor/lit.js` (16 КБ, self-contained).
- **Новый shim** `www/lit-base.js` реэкспортирует `LitElement`,
  `html`, `css` и базовые helpers.
- **Все 16 компонентов** + `sberhome-panel.js` используют
  `import { LitElement, html, css } from "./lit-base.js"`
  (или `"../lit-base.js"` в `components/`).  Поведение не изменилось
  для пользователей, у которых панель уже работала.

## [3.14.6] — 2026-04-22

### Fixed

- **Monitor / State Diffs** — значения дельт «прыгали» по горизонтали
  между блоками.  Каждый diff-блок рендерился в отдельной `<table>`
  с `table-layout: auto` — ширина колонок подстраивалась под
  содержимое, и блок «только added» без `from`/`arrow` получал
  другую раскладку, чем блок `changed + removed`.  Переключено на
  `table-layout: fixed` + явные ширины столбцов (`op 22px`,
  `key 240px`, `from 160px`, `arrow 24px`, `to auto`) — value-колонка
  теперь выстроена вертикально по всем блокам.
- **Panel layout** — контент всех вкладок (Devices, Monitor, Debug,
  Settings) упирался в левый/правый край панели.  Добавлен
  `padding: 16px` на `.content` (8px на мобилке).

---

## [3.14.5] — 2026-04-22

### Removed

- **`wrong_typed_value` check** дропнут из Schema Validator.  Sber
  REST/WS шлёт каждый атрибут со ВСЕМИ primitive `*_value` полями
  с zero-defaults (`""`, `"0"`, `0`, `false`) — см. реальный
  payload ниже.  Отличить «zero padding» от настоящего значения
  невозможно (`0W` / `humidity=0%` — валидные показания).
  Проверка выдавала false-positive на каждый атрибут — v3.14.4
  пытался спасти её через `is not None`, но defaults не `None`.

  ```json
  {"key":"online","type":"BOOL",
   "string_value":"","integer_value":"0","float_value":0,
   "bool_value":true,"enum_value":""}
  ```

### Changed

- **`missing_typed_value`** теперь срабатывает только когда
  ожидаемое поле **физически отсутствует** в dict'е.  Zero-value
  (`false`, `0`, `""`) больше не считаются «missing» — это
  легитимные показания.

---

## [3.14.4] — 2026-04-22

### Fixed

- **Schema Validation** — ложные `wrong_typed_value` warnings на
  каждом атрибуте.  `AttributeValueDto.to_dict()` сериализует все
  `*_value` поля (omit_none=False), из-за чего валидатор видел
  None-значения как «present» и для любого payload'а (`on_off`,
  `battery_percentage`, `temperature`, …) писал «type='BOOL'
  but payload also carries [enum_value, float_value, …]».
  Проверка присутствия теперь учитывает не-None значение.

### Added

- **AttrKey namespace** пополнен 16 ключами, которые Sber
  присылает в `reported_state`, но которых не было в нашем
  словаре (валидатор корректно writes `unknown_attr_key` info):
  `temp_unit_convert`, `bd_list_text_1`, `button_event`,
  `lighting_type`, `sms_pir`, `push_pir`,
  `sms_water_leak_state`, `push_water_leak_state`,
  `hvac_humidity`, `max_brightness_dawn`,
  `max_brightness_sunset`, `duration_dawn`, `duration_sunset`,
  `power_on_mode`, `signal_strength_dbm`, `light_scene`.

---

## [3.14.3] — 2026-04-22

### Первый публичный релиз

Нативная интеграция **Sber Smart Home** (приложение «Салют!») в
Home Assistant — полное покрытие APIа Sber Gateway API
(28 категорий устройств) + WebSocket push + встроенная панель
со встроенным DevTools.

Подробное описание возможностей — в [README.md](README.md).

---

История разработки до этого релиза собрана в один снимок; более
ранние коммиты и заметки хранятся только в старых клонах.
Следующие изменения будут логироваться здесь по мере выхода.
