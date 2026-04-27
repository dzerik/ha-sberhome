# Changelog

## [4.4.0] — 2026-04-27

### Added

- **`ScenarioAPI.run(scenario_id)`** — programmatic-run сценария через
  `POST /scenario/v2/scenario/{id}/run` (то же что кнопка «Запустить
  действие» в мобильном приложении Sber). Найдено через тщательный
  decompile-поиск (ScenarioGatewayImpl.runScenario).
- `IntentService.test_intent` теперь использует `client.scenarios.run()` —
  «Test now» в UI реально запускает Sber-side actions (TTS / device_command),
  через ~200 мс scenario_widgets WS push прилетает в HA и triggers
  `sberhome_intent` event автоматически (без ручного fire).

### Notes

В прошлых v4.2.x пробовали `POST /scenario/v2/command` (one-shot
ScenarioCommandDto-shaped) — Sber strict-валидирует condition shape,
точная schema не выводится. Endpoint `/run` проще: единственное
optional поле, реально запускает actions сценария.

## [4.3.2] — 2026-04-27

### Fixed

- **Modal сохраняет правки через internal `_draft`.** В v4.3.0 modal
  делал `this.intent = {...this.intent, ...}` в onChange handlers, но
  `intent` — это **prop** от parent. На любом re-render parent (например
  когда `hass` обновляется в HA — каждые ~1 сек!) Lit re-bind'ил
  `.intent=${this._editingIntent}` обратно, затирая модальные правки.
  Visible как «модалка постоянно сбрасывает все набранное».
- Modal копирует prop в private `_draft` через `willUpdate` ровно один
  раз при mount, дальше работает только с `_draft`.
- Defense-in-depth: parent intents-view skip'ает scenario_widgets
  event-driven refresh пока `_editingIntent != null`.

## [4.3.1] — 2026-04-27

### Added

- **Версия интеграции в шапке panel'а** (`SberHome v4.3.1` справа от
  заголовка). Версия читается из manifest.json (best-effort, кэшируется
  на module load), отдаётся через `sberhome/get_status` response.
  Упрощает диагностику когда пользователь репортит баг.

## [4.3.0] — 2026-04-27

### Added (Phase 11a.2: Voice Intents UI)

- **Новая вкладка «Voice Intents»** в SberHome panel.
- `sberhome-intents-view.js` — список intents с filter/search,
  last_fired_at column, бейджи (disabled / sber-only / fired ago).
  Live-update last_fired_at через event-bus subscription.
- `sberhome-intent-modal.js` — schema-driven create/edit форма:
  имя + phrases как chips (Enter → add) + enabled toggle + список
  actions со schema-driven полями.
- `sberhome-device-picker-field` — отдельный компонент device picker'а,
  дёргает `sberhome/intents/devices_for_picker`. **Возвращает все
  Sber-side устройства независимо от HA `enabled_device_ids`** —
  пользователь может выбрать колонку для TTS-action не подключая её в HA.
- Schema-driven форма: action_types через `intents/schema`, для
  каждого action рендерится свой набор полей из FieldSpec'ов.
  Добавили новый action_type на бэке — UI отрисует автоматически.
  Поддержанные FieldSpec types: text, number, bool, enum, multitext,
  device_picker.

## [4.2.2] — 2026-04-27

### Fixed

- `test_intent` через `POST /scenario/v2/command` падал с HTTP 400
  'wrong condition' независимо от формы condition. Workaround: fires HA
  `sberhome_intent` event с `simulated: true` без Sber-side execute.
  Окончательный fix в 4.4.0 через найденный `/run` endpoint.

## [4.2.1] — 2026-04-27

### Fixed

- `test_intent` через `POST /scenario/v2/command` падал с HTTP 400
  «invalid CreateCommandRequest.Name» — endpoint требует ScenarioCommandDto
  (name + tasks + condition), не {scenario_id: ...}. Промежуточная
  версия.

## [4.2.0] — 2026-04-27

### Added (Phase 11a.1: Voice Intents Backend)

Extensible backend для UI-managed Sber-сценариев:

- **`intents/spec.py`** — IntentSpec, IntentAction, FieldSpec
  dataclasses. Forward-compat: незнакомые Sber-поля сохраняются в
  `raw_extras` и мерджатся обратно при update.
- **`intents/registry.py`** — ActionRegistry pattern: 4 встроенных
  action_type (tts / device_command / trigger_notify / ha_event_only).
  Добавить новый = одна запись + 2 функции (encode/decode).
- **`intents/encoder.py`** — IntentSpec ↔ Sber `ScenarioDto` wire.
  Decoder парсит известные actions через registry, незнакомые
  оборачивает как `IntentAction(unknown=true)` сохраняя raw payload.
- **`intents/service.py`** — high-level CRUD над
  `coordinator.client.scenarios`, last_fired_at populated из event log.
- **8 WS endpoints**: `sberhome/intents/{list, get, create, update,
  delete, test, schema, devices_for_picker}`.

### Tests

65 новых: 13 spec / 15 registry / 11 encoder / 10 service / 16 websocket.
Live fixtures от probe Sber Gateway response.

## [4.1.1] — 2026-04-27

### Fixed

- Subscribe to `SCENARIO_WIDGETS` WS topic on handshake. В v4.1.0
  router.on(...) был зарегистрирован, но WebSocketClient по умолчанию
  подписывает только на `(DEVICE_STATE, DEVMAN_EVENT, GROUP_STATE)`.
  Sber-сервер не рассылает UPDATE_WIDGETS не-subscribed клиентам,
  поэтому voice-intent dispatcher никогда не срабатывал. Live-test
  после v4.1.0 deploy подтвердил баг.

## [4.1.0] — 2026-04-27

### Added

- **🎙️ Voice intents — голосовые команды Sber как HA-trigger'ы.**
  Каждый Sber-сценарий любого типа (TTS, push-нотификация, device
  command, что угодно), который сработал — fire'ит `sberhome_intent`
  HA event с `{name, scenario_id, event_time, type, account_id}`.
  Реализация через scenario_widgets WS топик + polling
  /scenario/v2/event endpoint'а, БЕЗ виртуальных кнопок-посредников.
  Latency ~300-500 мс end-to-end. См. README → «Voice intents»
  для готового automation snippet'а.
- `aiosber.dto.ScenarioEventDto` — типизированная обёртка над
  scenario history event log.
- `ScenarioAPI.history(home_id, *, offset, limit)` — `GET
  /scenario/v2/event` endpoint.
- `coordinator._on_ws_scenario_widgets` handler с throttling
  (`asyncio.Lock` + `INTENT_DISPATCH_COOLDOWN_SEC=1.0` для подавления
  duplicate WS push'ей которые Sber всегда шлёт парами ×2).
- Cursor-based dedup через `_last_intent_event_time`: на первом
  запуске берётся только самое свежее событие (иначе fire'ится весь
  history), дальше — все с `event_time > cursor`.

### Changed

- Coordinator больше не подписывает `Topic.SCENARIO_WIDGETS` на
  catch-all `_on_ws_other_topic` — у него теперь свой handler.

### Tests

- 14 новых тестов: 5 на `ScenarioAPI.history` (live shape +
  result-wrapper compat + garbled payload + filter non-dict items),
  9 на dispatcher (dedup на первом запуске, cursor-фильтр, payload
  shape, lock-based dedup duplicate push'ей, history-failure
  resilience, no-home_id skip).

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
