# Light effects + Sber custom-groups — дизайн

**Дата:** 2026-05-13
**Версия проекта на момент дизайна:** v5.3.0
**Целевой релиз:** v5.4.0 (MINOR — backwards-compatible)

## Контекст

В Sber Smart Home API есть две большие неиспользуемые в `ha-sberhome`
капабилити, которые мы видим в DTO/декомпиляции:

1. **Каталог световых эффектов** `GET /light/effects` (`LightEffectsAPI.list()`
   уже реализован). Лампы и LED-ленты могут переключаться в режим
   `light_mode=scene` и проигрывать выбранный эффект из этого каталога.
2. **Пользовательские группы устройств** (`UnionDto.group_type == GROUP` —
   например «Освещение прихожей»). Sber API позволяет отправлять
   bulk-команду на группу через `PUT /device_groups/{id}/state`
   (`GroupAPI.set_state()` уже реализован). В HA эти группы сейчас никак
   не представлены.

## Цель

Дать пользователю две связанные с light platform возможности без
введения новых config-параметров и без breaking changes:

- **Эффекты на лампах/лентах** через нативный HA-API
  (`light.turn_on entity_id: light.x effect: "Радуга"`).
- **Sber-группы как `switch` entities** для bulk-управления (например
  одна кнопка для группы «Освещение прихожей»).

## Решения по итогам brainstorming

1. API эффектов — **нативный HA `light.effect`** (через
   `LightEntityFeature.EFFECT` + `attr_effect_list` + `attr_effect`).
2. Sber-группы → **`switch` entity** на каждую (не `scene` и не
   light-group — `switch` подходит для mixed-составов и даёт toggle
   off, в отличие от scene).
3. Detection эффектов — **auto-detect по `light_mode.enum_values`**
   (показываем effects там, где firmware реально умеет `light_mode=scene`).

## Архитектура

### Effects

**Каталог эффектов** загружается единожды через `LightEffectsAPI.list()`
при `DeviceService.refresh()` (best-effort, аналогично существующему
кэшу `enums`):

- Новый storage в `StateCache`: `_light_effects: list[dict[str, Any]]`
  с полями `{id, name, preview?, category?}` + accessor
  `get_light_effects() -> list[dict]`.
- `DeviceService.refresh()` после успешного flat refresh догружает
  каталог если кэш пуст. Любая ошибка `/light/effects` логируется на
  DEBUG и НЕ валит общий refresh — поведение симметричное текущему
  fetch'у `/devices/enums`.

**Light platform integration** (расширение `light.py`):

При построении entity для devices с `category ∈ {light, led_strip}`
проверяется атрибут `light_mode` в `DeviceDto.attributes[]`:

- Если у атрибута `enum_values` содержит `"scene"` →
  - `_attr_supported_features |= LightEntityFeature.EFFECT`,
  - `_attr_effect_list = [name for {id, name} in catalog]`,
  - `_attr_effect = current_effect_name` (резолвится из
    `reported_state.light_scene` через reverse-map `id → name`;
    `None` если `light_mode != "scene"`).

Если эффектов в каталоге нет (пустой ответ Sber или сбой fetch) —
`_attr_effect_list = []`, и Lovelace автоматически скрывает
effect-dropdown — graceful degradation.

**Turn-on flow**:

```python
async def async_turn_on(self, **kwargs):
    if (effect := kwargs.get(ATTR_EFFECT)):
        effect_id = self._resolve_effect_id(effect)
        if effect_id is None:
            LOGGER.warning("Unknown effect %r — falling back to plain on", effect)
            # fall-through к обычному turn_on
        else:
            attrs = [
                AttributeValueDto.of_enum(AttrKey.LIGHT_MODE, "scene"),
                AttributeValueDto.of_string(AttrKey.LIGHT_SCENE, effect_id),
                AttributeValueDto.of_bool(AttrKey.ON_OFF, True),
            ]
            await self.coordinator.async_send_device_state(self._device_id, attrs)
            return
    # … обычный path on/off/brightness/color
```

### Groups

**Источник данных**: `state_cache.get_all_groups()` уже содержит
`UnionDto` с `group_type=GROUP` (HOME/ROOM пропускаются). При
`update_from_flat()` строится **reverse-index** `_devices_by_group:
dict[group_id, list[device_id]]` с публичным accessor'ом
`get_group_devices(group_id) -> list[str]`.

**Synthetic entities — `SberGroupSwitch(SwitchEntity)`**:

- `unique_id = f"sber_group_{group_id}"`.
- `name = group.name` (например «Освещение прихожей»).
- `device_info`: `manufacturer="Sber"`, `model="Group"`,
  `identifiers={(DOMAIN, f"group:{group_id}")}` — отдельный namespace,
  чтобы не конфликтовать с реальными устройствами.
- `available`: True если хотя бы одно устройство группы онлайн.
- `is_on`: aggregated — True если у любого device в группе
  `reported.on_off == True`. None если ни у одного device группы нет
  атрибута `on_off` (например группа только из cover-ов или датчиков).
- `async_turn_on/off`:

  ```python
  await self.coordinator.client.groups.set_state(
      self._group_id,
      [AttributeValueDto.of_bool(AttrKey.ON_OFF, True)],  # или False
  )
  # Optimistic patch: state_cache.patch_device_desired для каждого
  # device через get_group_devices(group_id).
  ```

  Sber сам разъезжает команду по устройствам серверной стороной.
  Никакого N-вызова к /devices/.../state не делаем.

**Платформа `switch.py`**:

В существующий `async_setup_entry` добавляется второй источник
entities — `_build_group_switches(coordinator)`. Возвращает
`SberGroupSwitch`-объекты, форвардятся вместе с device-switches.
Existing device-switches не трогаются.

**Edge cases**:

- Группа с 0 устройств → entity **не создаётся** (не загромождаем UI).
- Mixed-группы (лампы + шторы + розетки) → bulk on_off отправляется
  всем; cover/select-устройства Sber-side либо игнорируют, либо
  применяют per-feature логику. Не наше дело контролировать.
- Удалена группа в Sber-app → следующий refresh не вернёт её → entity
  становится `available=False`, удаляется HA при следующем reload.

### State + reactivity

- **Polling refresh** (30 сек / 10 мин при WS-live) пересоздаёт
  `state_cache._groups` целиком, reverse-index `_devices_by_group`
  тоже. После refresh coordinator вызывает `rebuild_caches_and_notify()`
  — все `SberGroupSwitch` через CoordinatorEntity-механизм
  пересчитывают `is_on/available`.
- **Discovery новых групп** (пользователь создал в Sber-app): на
  следующий refresh `coordinator.state_cache.get_all_groups()` вернёт
  новую группу. Platform-listener (`coordinator.async_add_listener`)
  через `async_add_entities` подкидывает `SberGroupSwitch` без
  рестарта integration'а. Удалённые группы → `available=False`.
- **WS-реактивность**: `DEVICE_STATE` push → `coordinator._on_ws_device_state`
  патчит `state_cache._devices` → group switch триггерится через
  CoordinatorEntity update. Добавим обработку `GROUP_STATE` push (сейчас
  только logged) — он будет тригерить `async_update_listeners()` чтобы
  агрегация пересчиталась мгновенно, не дожидаясь следующего polling.

### Lifecycle / unload

Никаких отдельных tasks/listeners в `SberGroupSwitch` — наследник
`CoordinatorEntity`, всё уходит вместе с coordinator на unload.
Аналогично effect-расширения light-entity. Никаких background-задач
не запускается.

## Тестовая стратегия (TDD-friendly)

Все тесты unit-уровня на mock-coordinator / mock-state_cache, без
HA hass-фикстур кроме platform setup.

### `LightEffectsAPI` (если ещё нет тестов)
- Парсинг трёх shape ответа: голый list, `{"effects": [...]}`,
  `{"result": ...}`.

### `StateCache`
- `test_state_cache_stores_light_effects`.
- `test_state_cache_devices_by_group_index` — после
  `update_from_flat()` reverse-index корректен.
- `test_state_cache_group_index_handles_device_in_multiple_groups`.

### `DeviceService.refresh()`
- `test_refresh_loads_light_effects_when_empty`.
- `test_refresh_light_effects_failure_does_not_block` — respx-мок
  возвращает 5xx → refresh успешен, `_light_effects = []`.

### Light platform — effects
- `test_effect_support_when_lightmode_has_scene`.
- `test_no_effect_support_for_simple_bulb` — `enum_values` без `scene`.
- `test_turn_on_with_effect_sends_correct_attrs` — `light_mode=scene`
  + `light_scene=<id>` + `on_off=true`.
- `test_current_effect_resolved_from_state` — `light_scene` value →
  effect name из каталога.
- `test_unknown_effect_name_logs_and_falls_back_to_plain_on`.
- `test_empty_catalog_no_effect_list`.

### Group switches
- `test_group_switch_aggregated_is_on_when_any_device_on`.
- `test_group_switch_is_on_none_when_no_on_off_devices`.
- `test_group_switch_turn_on_calls_group_set_state` — `GroupAPI.set_state`
  вызывается с правильным `group_id` и attr `on_off=True`. Подтверждаем
  что **не** делается N вызовов в `/devices/.../state`.
- `test_empty_group_not_exposed_as_entity`.
- `test_group_switch_unavailable_when_all_offline`.
- `test_group_switch_optimistic_patch_after_turn_on`.

### Platform setup
- `test_switch_platform_includes_group_switches` — `async_add_entities`
  получает и device-switches, и group-switches.
- `test_new_group_added_via_listener` — новый item в
  `state_cache._groups` после refresh → `async_add_entities` вызвана с
  новой entity.

**Итого ~20-25 новых тестов.** Все 1216 существующих остаются зелёные.

## Изменения по файлам

| Файл | Тип | Что |
|---|---|---|
| `aiosber/service/state_cache.py` | modify | `_light_effects`, `_devices_by_group` + accessors + populate в `update_from_flat()` |
| `aiosber/service/device_service.py` | modify | в `refresh()` best-effort fetch `/light/effects` |
| `light.py` | modify | auto-detect EFFECT через `light_mode.enum_values`; `turn_on` с `ATTR_EFFECT` |
| `switch.py` | modify | дополнительный источник entities: group-switches |
| `switch_groups.py` | **new** | `SberGroupSwitch(SwitchEntity)` + helpers |
| `coordinator.py` | minor | в `_on_ws_other_topic` для `GROUP_STATE` вызывать `async_update_listeners()` |
| `tests/aiosber/service/test_state_cache.py` | modify | +3 теста |
| `tests/aiosber/service/test_device_service.py` | modify | +2 теста |
| `tests/aiosber/api/test_effects.py` | new (if missing) | parsing tests |
| `tests/test_light_effects.py` | **new** | ~6 тестов |
| `tests/test_switch_groups.py` | **new** | ~7 тестов |
| `README.md` | minor | секция «Light effects + Sber-groups» |
| `CHANGELOG.md`, `pyproject.toml`, `manifest.json` | bump | 5.3.0 → 5.4.0 |

Размер PR: ~600-900 строк включая тесты и docs.

## Миграция и обратная совместимость

- **Без breaking changes.** Существующие light-entities получают
  дополнительный `EFFECT` feature flag (опционально, при auto-detect).
- Существующие switches не трогаются.
- Если у пользователя нет `group_type=GROUP` в Sber — никаких новых
  switch-entities не появится.
- Никаких новых параметров в `configuration.yaml`.

## Не входит в scope этого спека

- **Sber-group → light/`light.group`** — отложено: switch-варианта
  достаточно для UX. Если в будущем потребуется brightness/color
  aggregation для all-light groups — отдельный sub-проект.
- **Создание/удаление Sber-groups из HA** — пользователь по-прежнему
  управляет составом групп через приложение «Салют!».
- **Light effects через service-call (`sberhome.set_effect`)** —
  отложено: native HA `light.effect` достаточно.
- **Color correction** (`DeviceCorrectionDto.formula_type`) — отдельный
  sub-проект, не связан архитектурно с этим.

## Risks и mitigation

| Риск | Mitigation |
|---|---|
| Sber отдаст `/light/effects` в неожиданной shape | API уже tolerant (3 shape поддержаны), fallback на пустой list |
| Эффект с `light_scene` id не из каталога (legacy/новый firmware) | `_attr_effect = None` — корректное HA-поведение «no effect active» |
| User-defined группа содержит только устройства без `on_off` | Entity не создаётся (защита `_build_group_switches`) либо `is_on=None` |
| `GROUP_STATE` WS push содержит неполную информацию | Trigger `async_update_listeners()` опирается на текущий `state_cache`, не на содержимое push'а — устойчиво |
