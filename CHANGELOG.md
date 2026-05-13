# Changelog

## [5.1.7] — 2026-05-13

### Fixed

- **`full_categories` теперь парсится как массив объектов** (`list[
  DeviceCategoryDto]`), а не как массив строк. До v5.1.7 поле было
  типизировано неверно — `list[str]` — и `_serde.from_dict` молча
  игнорировал реальный JSON. Из-за этого slug категории, который Sber
  отдаёт явно (`full_categories[0].slug` = `"valve"` / `"led_strip"` /
  `"hvac_fan"`), не использовался при определении типа устройства.
- **`resolve_category()` теперь принимает `slug=` как авторитативный
  источник** (приоритет 0 над `image_set_type`). Если slug совпадает
  с известной категорией из `CATEGORY_TO_HA_PLATFORMS` — возвращается
  напрямую, без эвристического substring-парсинга `image_set_type`.

### Added

- **`DeviceDto.primary_category_slug`** — геттер, возвращающий
  `full_categories[0].slug` (первая категория) или `None`. Для
  multi-категорийных устройств (LED-ленты приходят как
  `[{slug:"led_strip"}, {slug:"light"}]`) возвращается первый
  элемент — основная категория устройства.
- **`resolve_device_category(dto)`** — удобный shortcut: достаёт
  оба источника (slug + image_set_type) и резолвит. Все call-sites
  (`light.py`, `climate.py`, `coordinator.py`, `websocket_api/*`,
  `sbermap/transform/mapper.py`) переключены на него.
- **`DeviceCategoryDto`** расширен полями `default_name`,
  `image_set_type`, `sort_weight` — соответствует реальной shape API.

### Compat

- Колонки Sber (SberBoom Home / SberPortal / SberBox) приходят с
  `slug="default"`. Это не валидная категория — резолвер
  автоматически идёт в fallback по `image_set_type`
  (`dt_boom_r2_*` → substring → `sber_speaker`). Поведение
  сохранено.
- Старая сигнатура `resolve_category(image_set_type)` продолжает
  работать без аргумента `slug`.

### Tests

- 12 новых тестов: парсинг `full_categories` объектов, slug-приоритет,
  fallback на `image_set_type` для `slug="default"`,
  `resolve_device_category(dto)` обёртка.

## [5.1.6] — 2026-05-13

### Mobile adaptation — все view-компоненты панели

Завершение mobile-адаптации, начатой в v5.1.5 (шапка + табы). Теперь
адаптируется **внутреннее содержимое** каждого таба:

**Главная таблица устройств** (`sberhome-device-picker`):
- На ≤768 px таблица превращается в **карточки**: `thead` скрыт,
  каждая `<tr>` — flex-block с иконкой устройства слева и информацией
  справа. Имя устройства занимает full-width на собственной строке,
  ниже — компактные badge-метки «комната», «категория», «статус» с
  заголовками через `::before`.
- Длинные имена не разрывают layout (`word-break: break-word`).
- Toolbar (поиск + dropdown категорий + counter) переносится на
  несколько строк через `flex-wrap`.

**Модальное окно устройства** (`sberhome-device-modal`):
- На ≤768 px — **полноэкранный** modal (`border-radius: 0`,
  `min-height: 100vh`), без padding-overlay.
- Header компактнее (photo 56 px вместо 72, h2 16 px).
- Под-табы внутри modal горизонтально-скроллируемые.
- `info-table` (пары th/td) → вертикальные блоки с metadata над
  значением.

**Все остальные view** (status / monitor / debug / settings /
intents / log / state-diff / diagnose / replay / commands /
validation / raw-command / rooms):
- Подключён shared mobile-CSS helper (`www/mobile-css.js`) через
  `static get styles() { return [css\`...\`, mobileBase]; }`.
  Baseline применяется ко всем стандартным контейнерам:
  - `.toolbar`, `.header`, `.filters`, `.row`, `.actions`,
    `.controls` — `flex-wrap: wrap; gap: 8px`.
  - inputs / selects / textareas — `font-size: 13px; min-width: 0`.
  - buttons — `min-height: 36px` (тач-target).
  - `pre`, `code` — `font-size: 11px; overflow-x: auto;
    word-break: break-word`.
  - generic `table` — `font-size: 12px; th/td padding 6/8 px`.

## [5.1.5] — 2026-05-12

### Changed

- **UI панели приведён к light/content-style** (взято из sister-проекта
  [MQTT-SberGate](https://github.com/JanchEwgen/MQTT-SberGate)). Раньше
  верхний bar был тёмный (`--app-header-background-color`) с
  полу-прозрачными pill-кнопками; теперь шапка и табы рисуются на
  обычном content-фоне с HA card-палитрой:
  - Заголовок `SberHome` крупнее (24px), под Sber-стандарт.
  - Refresh-кнопка единообразна с dropdown-ами выбора дома и
    категории — `padding: 8px 12px`, `border-radius: 6px`,
    `--card-background-color` фон.
  - Табы со стандартным HA-подчёркиванием через `--primary-color`,
    `text-transform: uppercase; letter-spacing: 0.5px`, transition
    при hover.
  - Группа header-actions (home-switcher + refresh-btn) с `flex-wrap`
    — на узких экранах переезжают на новую строку под заголовок.

### Mobile

- **Breakpoint увеличен с 600 до 768 px** — захватывает планшеты в
  portrait + телефоны.
- **Табы стали горизонтально-скроллируемыми** (`overflow-x: auto`,
  `-webkit-overflow-scrolling: touch`, скрытый scrollbar). На узких
  экранах таб-полоса не разрывается и не выталкивает контент.
- Уменьшен padding шапки (`8px` вместо `16px`), размеры табов
  (`10px 14px / 12px` font), error-banner.

## [5.1.4] — 2026-05-12

### Documentation

- `LEGAL.md`: развёрнут разбор п. 4.15 Условий использования
  виртуального ассистента «Салют». Добавлены три параграфа с честной
  правовой квалификацией:
  - «Использование программного кода» — wire-format протокола не
    является программным кодом в правовом смысле (ст. 1259 / 1261 ГК
    РФ), это отдельная категория (know-how / коммерческая тайна по
    ст. 1465 ГК РФ при соблюдении соответствующего режима, которого
    в данном случае нет).
  - «Имитация работы функций ассистента» — детальный список того, что
    мы не делаем (STT/TTS/NLP/SmartApps/voice-команды), и того, что
    делаем (read-only подписка на завершённые события).
  - **Новый раздел про `X-Device-ID`, User-Agent, `Referer`, `rsa_data`**
    — честная квалификация: это собственный UUID клиента и обязательные
    HTTP-поля для совместимости с сервером, а не имитация конкретного
    устройства или обход технических средств защиты (нет dec ryption,
    нет circumvention signature-check). Ссылка на hiQ Labs v.
    LinkedIn (US 9th Circuit) как близкий по духу прецедент.
- Таблицы заменены на bullet-списки для лучшего отображения в
  IDE-рендерерах и на GitHub.

## [5.1.3] — 2026-05-12

### Documentation

- Добавлен файл `LEGAL.md` с развёрнутой правовой позицией проекта:
  ст. 1280 ГК РФ, EU Software Directive 2009/24/EC, EFF Coders'
  Rights Reverse Engineering FAQ, разбор публичных документов
  SberDevices / Sber (Правила гарантийного обслуживания, Условия
  использования виртуального ассистента «Салют», C2C-документация).
  Описаны защитные ограничения проекта (только собственные credentials
  пользователя, no scraping, no MITM, атрибуция MIT-источников).
- В README добавлен раздел **Disclaimer**: явное указание на
  отсутствие аффилиации с ПАО Сбербанк / SberDevices, выделение
  публично задокументированного Sber ID OAuth flow как основного
  пути, ссылка на MIT-источник для бета-режима SMS-OTP, **nominative
  use** товарных знаков. Шаблон взят из `sboom_ha`.

Содержательных изменений в коде интеграции нет.

## [5.1.2] — 2026-05-12

### Fixed

- HACS validation: добавлены brand-assets
  (`custom_components/sberhome/brand/icon.png` + `icon@2x.png`).
  Раньше HACS-checker выдавал warning «repository does not contain
  brands assets».

## [5.1.1] — 2026-05-12

### Fixed

- CI: применён `ruff format` к 13 файлам — локально гонял только
  `ruff check`, без auto-format, отсюда регрессия. Поведение кода
  не меняется.

## [5.1.0] — 2026-05-12

### Added

- **SMS-OTP вход (beta)** — альтернативный путь авторизации через
  номер телефона + одноразовый код. Полезно тем, у кого стандартный
  `id.sber.ru` flow не отработал (блокировка `companionapp://`,
  баги мобильного браузера и т.п.). В config flow появилось меню
  выбора метода: «Sber ID (через браузер, рекомендуем)» или «Номер
  телефона + SMS-код (beta)».

  **Механизм и алгоритм взяты полностью из открытого источника —
  проекта [shuryak/sberdevices](https://github.com/shuryak/sberdevices)
  (Go, MIT)**. Endpoint'ы CSAFront (`/authenticate`, `/verify`,
  `/oidc/v3/token`, `/v13/smarthome/token`), anti-bot `rsa_data`,
  persistent `X-Device-ID`, refresh-rotation — переиспользованы без
  изменений по существу; портировано на Python/asyncio и
  интегрировано в общий `aiosber`-стек.

  Технически: `CsafrontTokens` (DTO с CSAFront access + refresh +
  SmartHomeToken + client_uuid), `CsafrontAuthManager` (тот же
  публичный API что у `AuthManager`: `access_token()` + `force_refresh()`),
  `HACsafrontTokenStore` (persist в `entry.data["csafront_tokens"]`).
  HttpTransport принимает оба менеджера через duck-typed
  `AuthManagerProtocol`. Reauth flow диспатчит на исходный метод
  по `entry.data["auth_method"]`.

- **`AuthManagerProtocol`** в `aiosber/auth/store.py` — runtime-checkable
  Protocol для duck-typing'а между `AuthManager` (SberID + companion)
  и `CsafrontAuthManager` (SMS-OTP). `HttpTransport` теперь типизирован
  на Protocol, не на конкретный класс.

### Changed

- **`coordinator.auth_manager`** теперь возвращает `AuthManagerProtocol`
  вместо `AuthManager` — может быть и `CsafrontAuthManager`.
- **UI**: dropdown «Все дома» в header панели приведён к единому
  стилю с dropdown «Все категории» (тот же `padding`, `border-radius`,
  HA-палитра через `--card-background-color` / `--divider-color`).
  Кнопка «Обновить» также подтянута под общий стандарт.

### Migration

Существующие entries не требуют действий — `entry.data["auth_method"]`
по умолчанию считается `sberid` (старый flow). Новые установки
проходят через меню выбора метода.

## [5.0.0] — 2026-05-12

Полная миграция координатора на типизированный стек `aiosber`. Удалён
устаревший `HomeAPI` shim и связанный с ним кеш raw dict. Все Sber-API
вызовы теперь идут через `coordinator.client.<domain>` (SberClient
фасад). Архитектурный долг из CLAUDE.md «парадигма пункт 6» закрыт.

Поведение для пользователя не меняется — это рефакторинг внутренних слоёв.
Bump до 5.0.0 потому что публичные внутренние API для расширений
(intents, custom services) меняются: `coordinator.home_api` больше нет.

### Changed (BREAKING для разработчиков расширений)

- **`coordinator.home_api` удалён**. Используйте `coordinator.client`
  (SberClient) или `coordinator.client.transport` для низкоуровневых
  запросов. AuthManager доступен через `coordinator.auth_manager`.
- **`HomeAPI` класс удалён из `api.py`**. AuthManager + HttpTransport
  теперь строятся напрямую в `async_setup_entry` и инжектятся в
  coordinator конструктор.
- **`SberHomeCoordinator.__init__` сигнатура изменилась**: вместо
  `(hass, entry, sber_api, home_api)` теперь
  `(hass, entry, sber_api, transport, auth_manager)`.
- **`entity._async_send_attrs`** использует
  `coordinator.async_send_device_state(device_id, attrs)` →
  `client.device_service.set_state(...)` с optimistic patch и
  единым retry на NetworkError.
- **`IntentService`** перешёл с `coord.home_api._transport` на
  `coord.client.transport`.
- **`send_raw_command` сервис** ходит через `coord.client.transport.put`
  напрямую (preserves raw-dict debug-fidelity, без AttributeValueDto
  парсинга).

### Removed

- `HomeAPI` класс целиком (был тонким shim'ом, все методы мигрированы).
- `HomeAPI.set_device_state`, `_set_device_state_inner`, `_request`,
  `_request_once` — функциональность доступна через
  `client.device_service.set_state` + `client.transport`.
- `HomeAPI._cached_devices` — source of truth теперь только
  `client.state` (StateCache).
- `tests/test_home_api.py` — тесты удалённого класса.

### Internal

- `coordinator.async_send_device_state(device_id, attrs)` — единая
  точка отправки команд с retry. Маппит в `client.device_service.set_state`.
- `COMMAND_RETRY_DELAY` константа переехала из `api.py` в `coordinator.py`.
- In-band code-16 retry теперь единым местом в `aiosber/transport/http.py`
  (был продублирован в `HomeAPI._request`).

### Migration guide (для custom-расширений)

| Было | Стало |
|---|---|
| `coord.home_api._transport.get(path)` | `coord.client.transport.get(path)` |
| `coord.home_api._auth` | `coord.auth_manager` |
| `await coord.home_api.set_device_state(id, dicts)` | `await coord.async_send_device_state(id, attrs)` |
| `await coord.home_api.get_auth_manager()` | `coord.auth_manager` (sync) |
| `await coord.home_api.aclose()` | (управляется coordinator.async_shutdown) |

## [4.8.0] — 2026-05-12

### Fixed

- **#2 Multi-home теперь реально работает.** v4.6.0/v4.7.0 закрывали UI
  + dispatcher слои, но `state_cache` грузился через
  `/device_groups/tree` — а этот endpoint single-home by design
  (отдаёт только дефолтный дом, параметры `home_id`/`union_id`
  игнорируются). В результате `get_homes()` всегда возвращал 1 дом,
  свитчер в панели не отображался у multi-home юзеров.

### Changed

- **`DeviceService.refresh()` теперь делает 4 параллельных flat-list
  запроса** вместо tree, и эти endpoints **multi-home aware**:
  - `GET /device_groups?group_type=HOME&pagination` — все дома аккаунта
  - `GET /device_groups?group_type=ROOM&pagination` — все комнаты всех домов
  - `GET /device_groups?group_type=GROUP&pagination` — кастомные группы
  - `GET /devices?pagination` — все устройства аккаунта
- **`StateCache.update_from_flat()`** строит mappings локально:
  - `room.parent_id == home.id` — room → home
  - `device.group_ids[0]` сматчится либо с room (значит device в
    комнате этого дома), либо с home (top-level, например SberBoom Home)
- **`GroupAPI.list(group_type=, limit=)`** — расширена, повторяет Salute
  pattern с `pagination.offset/limit`. Старый `/device_groups/` URL
  заменён на `/device_groups` без trailing slash + pagination params.
- **`DeviceAPI.list_flat(limit=500)`** — pagination-aware, нацелена на
  `/devices` (без trailing slash) с явным limit'ом.
- Legacy `update_from_tree()` остаётся как fallback при ошибке flat-API
  (single-home, deprecated).

### Removed

- `sberhome/debug/raw_tree` WS endpoint — был debug-only для разбора
  multi-home архитектуры, больше не нужен.

## [4.7.0] — 2026-05-12

### Added — Multi-home для intents/scenarios

Закрывает второе ограничение из v4.6.0 — теперь voice intents работают
корректно при наличии нескольких домов в Sber. Раньше dispatcher
обрабатывал только первый HOME, события из «Дачи» в `sberhome_intent`
не превращались.

- **Dispatcher (`coordinator._on_ws_scenario_widgets`)** теперь итерирует
  по `state_cache.get_homes()`, делая `history(home_id)` per home.
  Events fire'ятся независимо — событие из «Дачи» с `event_time` меньше
  cursor'а из «Мой дом» не теряется.
- **Cursor per home_id** — `_last_intent_event_time` теперь
  `dict[str, str | None]` вместо одного значения. Предотвращает потерю
  асимметричных timestamps между домами.
- **`IntentSpec.home_id`** — новое top-level поле (раньше home_id
  попадал в `raw_extras` через forward-compat). Encoder пишет в body
  при create — Sber кладёт сценарий в указанный дом вместо дефолтного.
- **`_populate_last_fired_at`** проходит по всем домам, объединяет
  events, выбирает максимальный `event_time` per scenario_id.
- **Intent modal** — dropdown «Дом» при create (если homes.length > 1).
  Default — `selectedHomeId` из panel state, либо `is_default=true` home.
  Для существующих intent'ов поле readonly (Sber не позволяет переместить
  через PUT — нужен delete+create).
- **Intents list** — фильтр по `selectedHomeId` из panel switcher'а.
  В режиме «Все дома» каждый intent несёт `🏡 имя_дома` badge.

### Limitations (документировано)

- Сменить дом существующего сценария через UI нельзя — Sber API не
  поддерживает move. Workaround: delete + create в новом доме.
- `at_home` переменная — глобальная для аккаунта (endpoint без
  home_id), multi-home не применимо.

## [4.6.1] — 2026-05-12

### Fixed

- **Двойная загрузка `sberhome-home-switcher` модуля → `customElements.define` падал с
  «name has already been used with this registry».** Причина: в `sberhome-panel.js`
  модуль импортировался дважды — один раз через `await Promise.all([import(...?v=X)])`
  с cache-busting querystring, второй раз через статический
  `import { HOME_SWITCHER_STORAGE_KEY }` без querystring. ESM считает URL'ы с
  разным query разными модулями → `define` вызывался дважды. Fix: storage-key
  инлайн в panel.js + защита `if (!customElements.get(...))` в самом switcher'е.

## [4.6.0] — 2026-05-12

### Added

- **#2 Multi-home UI filter в панели.** У юзеров с несколькими домами в Sber
  (например «Мой дом» + «Дача») появился dropdown-свитчер в header панели,
  позволяющий переключаться между домами. Состояние выбора хранится в
  `localStorage` ключом `sberhome.selected_home_id`. Если у юзера один дом
  — свитчер скрыт (`homes.length <= 1`).
- Подход — **lossless UI-only фильтр**: backend по-прежнему тянет все
  устройства из всех домов. HA entities, история, automations не
  затрагиваются. Только Devices/Debug вью в нашей панели фильтруют список
  по выбранному дому.
- `StateCache` теперь tracking-aware: `_walk_tree` пробрасывает
  `current_home_id` через subtree. Новые методы — `get_homes()`,
  `device_home_id(device_id)`, `device_home_name(device_id)`,
  `get_rooms(home_id=...)`. Legacy `get_home()` возвращает первый из
  `get_homes()` (для intents/scenarios).
- WS API: новая команда `sberhome/get_homes` (id/name/room_count/
  device_count/is_default), опциональный фильтр `home_id` в существующей
  `sberhome/get_rooms`. В `sberhome/get_devices` / `sberhome/device_detail`
  каждый device теперь несёт `home_id` и `home_name`.
- Новый компонент `sberhome-home-switcher.js` — drop-in в header,
  rendering пусто при ≤1 доме, валидация stale-state (если выбранный
  дом исчез из tree — сброс на «Все дома»).

### Out of scope (на будущее)

- **Multi-home для intents/scenarios** — пока работают только для
  первого HOME (legacy `state_cache.get_home()`). Расширение —
  отдельный PR.
- **Backend жёсткий фильтр** (`hidden_home_ids` в Options) — для юзеров,
  кто хочет полностью спрятать дом из HA. Делается по запросу.

## [4.5.0] — 2026-05-12

### Added

- **Smart token-fallback в `resolve_category`** — Sber-категория определяется
  по slug `image_set_type` через три уровня: exact match → phrase substring
  (отсортирован по длине, детерминизм) → token-window fallback по новому
  `CATEGORY_KEYWORDS`. Slug разбивается на токены по `_`, для каждого
  multi-token window ищется known keyword. Это автоматически покрывает
  новые префиксы Сбера (`cat_*`, `dt_*`, `xyz_*`) без ручного расширения
  `IMAGE_TYPE_MAP`. Длинные phrase-keywords (`sensor_temp_humidity`,
  `hvac_underfloor_heating`) имеют приоритет над short single-token.
- Конфликт-проверка на load: один keyword → одна категория, иначе
  `ValueError` на импорте модуля. Раньше зависимость от insertion order
  была хрупкой.

### Fixed

- **#1 Умная лента Sber SBDV-00055 (`image_set_type: cat_ledstrip_m`)** —
  раньше попадала в `resolve_category` → `None`, устройство игнорировалось
  с сообщением "категория не распознаётся". Теперь резолвится через
  token-fallback (`ledstrip` ∈ keywords для `led_strip`). Категория
  `led_strip` сама по себе полноценно поддержана: Platform.LIGHT + NUMBER
  для sleep_timer, расширенный CCT-range 2000–6500K.
- Аналогично закрыты потенциальные дыры покрытия: `cat_light_*` (умные
  лампы, артефакт `cat_light_basic` встречается в diagnose-payload'ах),
  `cat_vacuum_*` (роботы-пылесосы).

## [4.4.2] — 2026-04-27

### Fixed

- **GitHub Release re-publish для HACS visibility.** v4.4.0 и v4.4.1 release
  застряли в индексе GitHub orphaned (страница releases показывала "There
  aren't any releases here", `/releases` API list возвращал пусто) после
  серии delete/recreate-операций над v4.4.0. v4.4.2 — clean re-publish:
  старые broken tags+releases удалены, новый tag v4.4.2 от свежего commit'а.
  Содержимое идентично v4.4.0 (Voice Intents Phase 11 + полный 4.x цикл).

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
