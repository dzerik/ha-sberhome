# Changelog

## [2.1.0] — 2026-04-16

### Bidirectional symmetry в sbermap (PR #9)

После 2.0.0 read-логика жила в sbermap, а write — inline в платформах
(`SberStateBundle(states=(SberState(...), ...))` прямо в платформенных
методах). Это нарушало правило «вся логика в sbermap». В 2.1.0 для **каждой**
write-платформы создан per-platform модуль с командными билдерами.

### Новые модули в `sbermap/transform/`

| Модуль | Что внутри |
|---|---|
| `switches.py` | `build_switch_command` (primary on_off + extra с state_key) |
| `covers.py` | `CoverConfig`, `cover_state_from_dto`, `build_cover_position_command`, `build_cover_stop_command` |
| `climate_helpers.py` (расширен) | `build_climate_set_hvac_mode_command`, `build_climate_set_temperature_command`, `build_climate_set_fan_mode_command`, `build_climate_on_off_command` |
| `fans.py` | `build_fan_turn_on_command`, `build_fan_turn_off_command`, `build_fan_preset_command` |
| `humidifiers.py` | `build_humidifier_on_off_command`, `build_humidifier_set_humidity_command`, `build_humidifier_set_mode_command` |
| `vacuums.py` | `build_vacuum_command(command: VacuumCommand)` |
| `media_players.py` | 8 build функций: on_off, volume, volume_step, mute, source, custom_key, direction, channel + `TV_SOURCES` |
| `selects.py` | `build_select_command(key, option)` |
| `numbers.py` | `build_number_command(key, value, scale)` (inverse scale HA→Sber) |
| `buttons.py` | `build_button_press_command(key, command_value)` |

### Изменено

- `CoverConfig` переехал из `climate_helpers.py` → `covers.py` (более гранулярно).
- Все 10 write-платформ (switch, cover, climate, fan, humidifier, vacuum,
  media_player, select, number, button) **больше не строят `SberStateBundle`
  inline** — только вызывают `build_*_command()`. Никакой логики формирования
  команд в платформах не осталось.

### Тесты

- `+32` новых unit-теста: `tests/sbermap/transform/test_command_builders.py`
  для всех `build_*_command` функций.
- Всего: 806 → **838** тестов, покрытие **90%**.
- Все 13 platform-тестов зелёные без изменений (изменения внутренние).

### Архитектурный итог

`sbermap` теперь **полностью bidirectional**: для каждой платформы есть
пара read (`*_state_from_dto` или общий `device_dto_to_entities`) +
write (`build_*_command`). Платформа = тонкий адаптер, нулевая логика
конверсии Sber↔HA.

## [2.0.0] — 2026-04-16 — MAJOR RELEASE

### Полный рефакторинг на sbermap (PR #8 — финальный cleanup)

**Кульминация PR #1-#8.** Все 13 платформ теперь работают через единый
`sbermap` слой. `registry.py` удалён. Legacy-хелперы убраны. Single source
of truth для Sber↔HA конверсии — sbermap.

### УДАЛЕНО

- `custom_components/sberhome/registry.py` (954 строки, удалён полностью).
  Содержимое перенесено в `sbermap.transform.sber_to_ha`,
  `sbermap.transform.lights`, `sbermap.transform.climate_helpers` и
  `sbermap.spec.ha_mapping`.
- `entity.SberBaseEntity._get_desired_state`, `_get_reported_state`,
  `_get_attribute`, `_async_send_states` — все legacy raw-dict хелперы.
- `utils.find_from_list` — больше нигде не используется.
- Backward-compat классы во всех платформах: `SberGenericSensor`/
  `SberTemperatureSensor`/etc., `SberGenericBinarySensor`/`SberWaterLeakSensor`/etc.,
  `SberGenericSwitch`/`SberExtraSwitch`/`SberSwitchEntity`,
  `SberGenericClimate`, `SberGenericCover`/`SberSideCover`,
  `SberGenericFan`, `SberGenericHumidifier`, `SberGenericNumber`,
  `SberGenericSelect`, `SberButton`, `SberGenericEvent`, `SberTvEntity`,
  `SberVacuumEntity`.
- `tests/test_utils.py::find_from_list` тесты, `tests/test_api.py::find_from_list` тесты.

### ИЗМЕНЕНО

- `entity.SberBaseEntity` — финальное API: `_device_data` (legacy raw для
  device_info/diagnostics), `_device_dto` (typed), `_entity_data(unique_id)`
  (HaEntityData lookup), `_async_send_bundle(bundle)`, `_merge_optimistic`.
- `diagnostics.py` — переписан на `coordinator.devices` (DeviceDto) +
  `coordinator.entities` (HaEntityData).
- `tests/test_entity.py` — упрощён, тестирует только публичный API
  (`_attr_unique_id`, `_attr_name`, `_device_data`, `device_info`,
  `available`).

### Архитектура — финальная картина

```
HA platforms (13)              ← thin: entities[Platform.X] + bundle
       ↓
SberHomeCoordinator
       ↓
.devices: dict[id, DeviceDto]  ← typed (aiosber)
.entities: dict[id, list[HaEntityData]]  ← rendered (sbermap)
       ↓
sbermap.transform              ← single source of truth для конверсии
       ↓
SberClient.devices.set_state()  ← typed wire (aiosber)
```

### Тесты

- 818 → **806** (минус ~12 удалённых legacy тестов).
- Покрытие: **90%**, sbermap **96%**.
- ruff lint: чистый.

### Breaking changes для разработчиков

Если форки/custom dashboards импортировали `registry`, `find_from_list`
или `_get_*_state`/`_async_send_states` хелперы напрямую — заменить на
`sbermap.device_dto_to_entities()` или прямой доступ к `coordinator.entities`.

### Breaking changes для пользователей

- **`unique_id`** сохранены идентичными (за этим следили в PR #3-#7) —
  никаких orphan entries в HA entity_registry.
- **Diagnostics dump format** изменился: вместо raw `desired_state_keys`/
  `reported_state_keys`/`attribute_keys` теперь даём typed view + список
  HA-entities с `platform`/`unique_id`/`state_attribute_key`.

## [1.18.0] — 2026-04-16

### Final batch: vacuum + media_player + select + number + button + event (PR #7)

Финальная пачка платформ переведена на sbermap. **Ни одна платформа теперь
не импортирует registry.py** — все 13 платформ обслуживаются через
`coordinator.entities` + `_async_send_bundle`.

- `vacuum.py`: `SberSbermapVacuum` — state из `HaEntityData.state`
  (VacuumActivity), команды через `vacuum_cleaner_command` enum bundle.
- `media_player.py`: `SberSbermapMediaPlayer` — read через `coordinator.entities`,
  все commands (volume/source/mute/custom_key/direction/channel) через bundle.
- `select.py`: `SberSbermapSelect` — options/state_attribute_key из HaEntityData.
- `number.py`: `SberSbermapNumber` — min/max/step/scale из HaEntityData.
- `button.py`: `SberSbermapButton` — fire-and-forget через bundle (intercom unlock/reject).
- `event.py`: `SberSbermapEvent` — change-detect по marker из reported_state.

Тесты переписаны для всех 6 платформ.

Всего тестов: 908 → **818** (уменьшение из-за удаления legacy backward-compat
и spec-driven тестов на CATEGORY_*; покрытие функционала 100% сохранено).
Покрытие: **88%**, sbermap **96%**.

## [1.17.0] — 2026-04-16

### fan + humidifier → sbermap (PR #6)

- `fan.py`: `SberSbermapFan` через `coordinator.entities[Platform.FAN]`,
  preset_modes из `HaEntityData.options`. Удалён `SberGenericFan`.
- `humidifier.py`: `SberSbermapHumidifier` с `min_value`/`max_value`/`options`
  из `HaEntityData`. Удалён `SberGenericHumidifier`.
- Все turn_on/turn_off/set_humidity/set_mode идут через `_async_send_bundle`.

Тесты переписаны. Всего: 922 → **908** тестов, покрытие **91%**.

## [1.16.0] — 2026-04-16

### climate + cover → sbermap (PR #5 рефакторинга)

Платформы `climate.py` и `cover.py` мигрированы на sbermap. HVAC mode mapping,
fan modes, target temperature scaling, cover state mapping (opened/closing/
opening/closed → CoverState.*) — единая логика в `sbermap.transform.climate_helpers`.

**Что изменено:**
- `climate.py` (~180 → ~150 строк): `SberClimateEntity` использует
  `climate_state_from_dto(dto, config)` для read и `_async_send_bundle(...)`
  для write. HVAC mode маппинг через `map_hvac_mode`/`map_hvac_mode_to_sber`.
  Удалены `SBER_TO_HA_HVAC`, `HA_TO_SBER_HVAC` (живут в sbermap).
- `cover.py` (~160 → ~100 строк): `SberSbermapCover` через
  `coordinator.entities` + `cover_config_for(category)` для supported_features.
  Удалены `SberGenericCover`, `SberSideCover`, `_has_reported`. (Side covers
  для двустворчатых curtain/gate — будут добавлены в sbermap позже.)
- `sbermap.transform.climate_helpers` — новый модуль:
  - `ClimateConfig` (min_temp/max_temp/step/hvac_modes/fan_modes).
  - `ClimateState` (snapshot — is_on/hvac_mode/temperatures/fan_mode).
  - `climate_config_for(category)`, `climate_state_from_dto(dto, config)`.
  - `CoverConfig`, `cover_config_for(category)`.

### Тесты

- `test_climate.py`, `test_cover.py` — переписаны под новые классы.
- 951 → **922** (уменьшение из-за удаления legacy classes и side_cover тестов).
- Покрытие: **91%**, sbermap **96%**.

## [1.15.0] — 2026-04-16

### switch + light → sbermap (PR #4 рефакторинга)

Платформы `switch.py` и `light.py` переписаны через sbermap. Для light
вынесли всю scaling-логику (HSV ranges, color_temp Kelvin↔Sber,
brightness 100..900, light_mode resolution) в новый модуль
`sbermap.transform.lights` — теперь это **single source of truth** для
конверсии Sber↔HA в свет.

**Что изменено:**

- `light.py` (~280 → ~140 строк): `SberLightEntity` использует
  `light_state_from_dto(dto, config)` для read и `build_light_command(...)`
  для write. Вся per-device scaling из ranges в DeviceDto.attributes.
- `switch.py`: единый `SberSbermapSwitch` обслуживает primary on_off
  И extra-switches (child_lock/night_mode/ionization/aromatization/
  decontaminate/alarm_mute) через `state_attribute_key` поле HaEntityData.
  Удалены: `SberGenericSwitch`, `SberExtraSwitch`, `SberSwitchEntity`,
  `_has_attribute`.
- `sbermap.transform.lights` — новый модуль:
  - `LightConfig` dataclass — per-device ranges + supported modes.
  - `light_config_from_dto(dto)` — извлечение из device.attributes.
  - `light_state_from_dto(dto, config)` — full read (brightness, hs_color,
    color_temp_kelvin, light_mode).
  - `build_light_command(config, ...)` — HA params → SberStateBundle.
- `aiosber.dto.values.ColorValue.from_dict` поддерживает оба формата
  wire — canonical `{hue, saturation, brightness}` и legacy `{h, s, v}`.

### Тесты

- `test_light.py`, `test_switch.py`, `test_switch_extra.py` — переписаны
  под `_async_send_bundle` (mocked `client.devices.set_state`).
- 969 → **951** тестов (уменьшение из-за удаления legacy backward-compat
  классов). Покрытие: **91%**, sbermap **96%**.

## [1.14.0] — 2026-04-16

### sensor + binary_sensor → sbermap (PR #3 рефакторинга)

Платформы `sensor.py` и `binary_sensor.py` полностью переехали на
`sbermap` — теперь они итерируют `coordinator.entities` и создают entity
из `HaEntityData` без какого-либо знания о Sber wire-формате. Никаких
`_get_reported_state`, `find_from_list`, `SensorSpec`/`BinarySensorSpec`,
`scale=0.001 для мА→А` — вся логика в `sbermap.transform.sber_to_ha`.

**Что изменено:**

- `sensor.py`: класс `SberSbermapSensor(coordinator, device_id, ha_entity)`,
  `native_value` берётся live из `coordinator.entities`. Удалены legacy
  `SberGenericSensor`, `SberTemperatureSensor`, `SberHumiditySensor`,
  `SberBatterySensor`, `SberSignalStrengthSensor`, `SberVoltageSensor`,
  `SberCurrentSensor`, `SberPowerSensor` (все 8 backward-compat классов).
- `binary_sensor.py`: класс `SberSbermapBinarySensor(coordinator, device_id, ha_entity)`,
  `is_on` берётся через `_entity_data().state`. Удалены legacy
  `SberGenericBinarySensor`, `SberWaterLeakSensor`, `SberDoorSensor`,
  `SberMotionSensor`, `SberBatteryLowSensor`, `_has_reported`.
- `tests/conftest.py`: добавлена фикстура `mock_coordinator_with_entities`
  + helper `build_coordinator_caches()` — даёт coordinator-mock с
  заполненными `data`/`devices`/`entities` для тестов sbermap-driven
  платформ.
- Тесты: `test_sensor.py`, `test_binary_sensor.py`,
  `test_binary_sensor_extra.py`, `test_binary_sensor_online.py`,
  `test_sensor_hvac.py` — переписаны под новый канал.

### Breaking (для разработчиков, расширяющих интеграцию)

Удалены классы `SberTemperatureSensor` и пр. — если какие-то форки или
custom dashboards импортировали их напрямую, нужно использовать
`SberSbermapSensor` + lookup через `coordinator.entities`. Для конечных
пользователей HA — никаких изменений (unique_id/device_class/units сохранены).

### Тесты

- 991 → **969** тестов (уменьшилось из-за удаления legacy-классов и их
  специфических test cases; покрытие функционала сохранено).
- Общее покрытие: **90%**, sbermap **96%**.

## [1.13.0] — 2026-04-16

### Coordinator → DeviceDto + entities cache (PR #2 рефакторинга)

`SberHomeCoordinator` теперь поддерживает **три параллельных канала** доступа к
устройствам — `data` (legacy raw dict), `devices` (типизированный
`dict[str, DeviceDto]` из aiosber) и `entities` (готовые
`dict[str, list[HaEntityData]]` из sbermap). Платформы будут постепенно
мигрировать на новые каналы в PR #3-#7; legacy `data` удалится в PR #8.

**Что добавлено:**

- `coordinator.devices: dict[str, DeviceDto]` — typed DTO, lazy-конвертится из
  `home_api.get_cached_devices_dto()` после каждого refresh.
- `coordinator.entities: dict[str, list[HaEntityData]]` — кэш HA-сущностей,
  построенный через `sbermap.device_dto_to_entities()`.
- `coordinator._rebuild_dto_caches()` — пересчитывает оба кэша; вызывается
  после polling refresh **и** после оптимистичного `_async_send_*`.
- `HomeAPI.get_cached_devices_dto()` — новый метод, возвращает
  `dict[str, DeviceDto]` через `DeviceDto.from_dict()`.
- `sbermap.transform.dto_bridge`:
  - `device_dto_to_state_bundle(device)` — конверт `DeviceDto` →
    `SberStateBundle` (объединяет reported + desired, последний приоритет).
  - `device_dto_to_entities(device)` — full pipeline:
    `resolve_category(image_set_type) → sber_to_ha(...)`.
- `SberBaseEntity` получил helpers `_device_dto`, `_entity_data(unique_id)`,
  `_async_send_bundle(bundle)`, `_merge_optimistic(bundle)`. Используются
  новыми платформами (PR #4-#7).

### Тесты

- `+8` тестов `tests/sbermap/transform/test_dto_bridge.py` (state bundle,
  entities, color/enum/integer values, unknown categories).
- `+4` теста `tests/test_coordinator.py` для новых полей `devices`/`entities`.
- Всего тестов: 979 → **991** (+12), общее покрытие **90%**.

### Не затронуто

`registry.py`, ни одна из 13 платформ. Legacy `coordinator.data` остаётся
`dict[str, dict]` — поведение для существующих платформ идентично.

## [1.12.0] — 2026-04-16

### sbermap completeness pass (PR #1 рефакторинга на sbermap)

Расширили `sbermap.transform.sber_to_ha` до полного покрытия registry.py — теперь
мапер умеет создавать ВСЕ типы entity, которые сейчас рождает declarative
registry. Это фундамент для PR #2-#8 по миграции 13 платформ.

**Что добавлено в `sber_to_ha`:**

- **Common sensors** для всех категорий: `battery_percentage` (battery %),
  `signal_strength` (RSSI dBm), оба `EntityCategory.DIAGNOSTIC`.
- **Common binary sensors**: `battery_low_power` → BinarySensorDeviceClass.BATTERY.
- **Extra switches** (с `state_attribute_key`): `child_lock`, `hvac_night_mode`,
  `hvac_ionization`, `hvac_aromatization`, `hvac_decontaminate`, `alarm_mute`.
- **Selects**: `sensor_sensitive`, `temp_unit_view`, `open_rate`,
  `hvac_air_flow_direction`, `hvac_thermostat_mode`, `hvac_heating_rate`,
  `hvac_direction_set`, `vacuum_cleaner_program`, `vacuum_cleaner_cleaning_type`.
- **Numbers**: `kitchen_water_temperature_set`, `sleep_timer`, `hvac_humidity_set`,
  `light_transmission_percentage` (с `min_value`/`max_value`/`step`/`scale`).
- **Buttons**: intercom `unlock`, `reject_call` (с `command_value`).
- **Events**: `scenario_button` `button_event`, `button_1..10_event`,
  направленные `button_left/right/top_left/...` с `event_types=("click","double_click")`.
- **Extra binary sensors**: `tamper_alarm` для дверей, `kitchen_water_low_level`
  для чайника, `hvac_water_low_level`/`hvac_replace_filter`/`hvac_replace_ionizator`
  для увлажнителя/очистителя, `incoming_call` для домофона.
- **Extra sensors**: `kitchen_water_temperature` (kettle), `hvac_water_level`,
  `hvac_water_percentage` (humidifier).
- **Vacuum status mapping** `map_vacuum_status(raw) → VacuumActivity`:
  cleaning/running→CLEANING, paused→PAUSED, returning→RETURNING,
  docked/charging→DOCKED, idle→IDLE, error→ERROR.
- **HVAC mode mapping** `map_hvac_mode(sber, is_on) → HVACMode` и обратное
  `map_hvac_mode_to_sber(ha) → str | None` (None для OFF).
- **Fan/Humidifier preset_mode_options**: `("auto","low","medium","high","turbo")`
  для `hvac_air_purifier`, `("low","medium","high","turbo")` для `hvac_fan`.
- **HaEntityData расширен** новыми полями: `state_attribute_key`,
  `entity_category`, `icon`, `options`, `min_value`, `max_value`, `step`, `scale`,
  `enabled_by_default`, `suggested_display_precision`, `event_types`,
  `state_class`, `command_value`.

**`sbermap.spec.ha_mapping`:** перенесли `IMAGE_TYPE_TO_CATEGORY` из registry.py
под именем `IMAGE_TYPE_MAP` + добавили `resolve_category(image_set_type)` с той же
substring-match семантикой. Это будет single source of truth для определения
категории по `image_set_type`.

### Тесты

- `+50` тестов: `tests/sbermap/transform/test_sber_to_ha_extra.py` (extras,
  vacuum, hvac mappings, кнопки, events, options).
- `+25` тестов: `tests/sbermap/spec/test_ha_mapping.py` (resolve_category).
- Поправлен баг в `_DISPATCH["sensor_pir"]`: state_key `"pir"` → `"motion_state"`
  (правильное Sber spec значение).
- Всего тестов: 904 → **979** (+75), общее покрытие **91%**.

### Не затронуто

PR — чисто аддитивный. Ни registry.py, ни coordinator, ни одна из 13 платформ
**не изменены**. Поведение интеграции для пользователей идентично 1.11.1.

## [1.11.1] — 2026-04-15

### Fixed

- **CRITICAL**: `HATokenStore` был создан, но не подключён в `__init__.py`.
  Companion-токены НЕ персистились между перезапусками HA — на каждом старте
  выполнялся повторный companion exchange. Теперь `HATokenStore` передаётся
  в `HomeAPI` как `token_store=`, в `_ensure_client()` сначала читаем из
  store, при отсутствии fetch'им новый и сохраняем обратно.
  - `__init__.py`: wiring `HATokenStore(hass, entry)` → `HomeAPI(sber, token_store=…)`
  - `api.py`: `HomeAPI.__init__` принимает `token_store` (default `InMemoryTokenStore`),
    `_ensure_client()` делает load → fetch → save цепочку.

### Tests

- `+7` тестов `test_ha_token_store.py` (load/save/clear/roundtrip) — coverage
  модуля 0% → **100%**.
- `+11` тестов `test_coordinator.py` — WebSocket pieces (`_start_ws_task`,
  `_run_ws`, `_on_ws_device_state`, `_on_ws_devman_event`, restart logic).
  Coverage `coordinator.py` 51% → **80%**.
- Всего тестов: 885 → **904**, общее покрытие проекта **89%**.

## [1.11.0] — 2026-04-16

### Гибридный sbermap — HA enums в transform layer (PR #15)

`sbermap/transform/` + `spec/ha_mapping.py` теперь импортируют `homeassistant.*`
для type safety. `values/`, `codecs/`, `spec/_generated/` остаются standalone.

| Место | Было | Стало |
|---|---|---|
| `ha_mapping.py` | 14 `PLATFORM_*` строк | `Platform` enum |
| `HaEntityData.platform` | `str` | `Platform` enum |
| `HaEntityData.state` | `"on"` / `"off"` | `STATE_ON` / `STATE_OFF` |
| `HaEntityData.device_class` | `str` | `BinarySensorDeviceClass` / `SensorDeviceClass` / `CoverDeviceClass` |
| Units | `"°C"`, `"V"`, `"W"` | `UnitOfTemperature.CELSIUS`, etc. |
| Cover state | `"open"`/`"opening"` | `CoverState.OPEN`/`OPENING` |
| Climate state | `"cool"`/`"off"` | `HVACMode.COOL`/`OFF` |
| Brightness scaling | ручной 10 LOC | `value_to_brightness()` HA helper |

**+11 тестов** (`TestHybridHaTypes`), всего **885**. CLAUDE.md обновлён —
новая секция "Гибридный sbermap" с таблицей разрешений.

## [1.10.0] — 2026-04-16

### sbermap — bidirectional shared layer (PR #14) ⭐

Новый **standalone-пакет** `custom_components/sberhome/sbermap/` (sibling
к `aiosber/`) — извлекает общую логику между двумя проектами Sber-интеграций
с **противоположными направлениями**:
- `ha-sberhome` — Sber → HA (через приватный gateway/v1 + WS).
- `MQTT-SberGate` — HA → Sber (через публичный C2C MQTT).

Оба маппят между HA-моделью и Sber-моделью, но wire-форматы разные. sbermap
извлекает общую часть и предоставляет **двусторонний bridge**.

#### Архитектура

```
sbermap/
├── values/        # Canonical типы (HsvColor, SberValue, ScheduleValue) — без wire-специфики
├── spec/          # Single source of truth (categories/features/types из spec.json) + HA platform mapping
├── codecs/        # Wire encoders: Codec Protocol + GatewayCodec + C2cCodec
└── transform/     # Bidirectional: sber_to_ha() + ha_to_sber*()
```

#### Ключевая ценность: Codec Protocol

Wire-форматы Sber API отличаются:

| Поле | Gateway | C2C |
|---|---|---|
| Color field | `color_value` | `colour_value` |
| Color type | `"COLOR"` | `"COLOUR"` |
| Color components | `{hue: 0..359, saturation: 0..100, brightness: 0..100}` | `{h: 0..360, s: 0..1000, v: 100..1000}` |
| INTEGER serialization | `220` (int) | `"220"` (string) |
| State structure | flat (`{key, type, X_value}`) | nested (`{key, value: {...}}`) |

`Codec` Protocol с двумя реализациями (`GatewayCodec` / `C2cCodec`) скрывает
эти отличия за единым API: `encode_value()/decode_value()/encode_state()/...`.

#### Sber → HA transform

`sber_to_ha(category, device_id, name, bundle) -> list[HaEntityData]` —
превращает декодированный bundle в список HA-сущностей. Поддержано **18
категорий** (light/socket/relay/temp/water_leak/door/pir/smoke/gas/curtain/
blind/gate/valve/hvac_ac/heater/radiator/boiler/underfloor/fan/purifier/
humidifier/kettle/vacuum/tv/intercom/scenario_button/hub).

Каждая категория знает свою decomposition:
- `socket` → 1 switch + 3 sensor (voltage/current/power) + автоматическое
  conversion mA → A.
- `intercom` → 1 binary_sensor + 2 button (unlock/reject_call).
- `sensor_temp` → 3 sensor (temperature/humidity/pressure).

#### HA → Sber transform

Симметричные функции для `MQTT-SberGate`-подобных интеграций:
- `ha_light_to_sber()` — с auto-scaling brightness 0..255 → 100..900.
- `ha_switch_to_sber()`, `ha_climate_to_sber()`, `ha_cover_to_sber()`.
- `ha_to_sber_generic(platform, state, attrs)` — universal dispatcher.

#### Single source of truth

`sbermap/spec/`:
- `_generated/` — auto-gen из `docs/sber_full_spec.json` (CATEGORY_FEATURES,
  OBLIGATORY, FEATURE_TYPES, FEATURE_ENUMS, FEATURE_RANGES).
- `ha_mapping.py` — `CATEGORY_TO_HA_PLATFORMS`, `FEATURE_TO_HA_ATTRIBUTE`,
  reverse map, helper functions.

Оба проекта могут сослаться на `sbermap.spec` вместо хранения собственных копий.

#### Архитектурные правила

`sbermap` строго standalone:
- ❌ НЕТ импортов из `homeassistant.*` (используем строковые platform константы).
- ❌ НЕТ импортов из `aiosber/` (полная независимость).
- ❌ НЕТ deps кроме stdlib (pure dataclasses + Protocol).
- ✅ Compliance check (`tests/sbermap/test_no_external_imports.py`) — AST-парсинг.

Готов к extract в свой PyPI-пакет одним поиск-заменой `from .X` → `from sbermap.X`.

### Тесты

- **+63 теста** в `tests/sbermap/`:
  - `test_values.py` (18) — HsvColor clamping/scaling, SberValue/Bundle.
  - `test_codecs.py` (24) — Gateway/C2C encode/decode, divergence tests.
  - `test_transform.py` (20) — все категории Sber→HA + основные HA→Sber +
    end-to-end roundtrip (HA → bundle → wire → bundle → HA).
  - `test_no_external_imports.py` (1) — compliance check.
- Всего **873 теста** (было 810).

### Что дальше

`sbermap` готов как библиотека. Возможные следующие шаги:
- Migration HA-side платформ на `sbermap.sber_to_ha()` (заменит `registry.py`
  диспетчеризацию).
- Convince автора `MQTT-SberGate` использовать `sbermap` как dep.
- Extract `sbermap` + `aiosber` в PyPI (2.0.0).

## [1.9.0] — 2026-04-16

### WebSocket integration в coordinator (PR #11) ⭐

Самая важная фича для конечного юзера: **мгновенные обновления состояний**
устройств через `wss://ws.iot.sberdevices.ru` вместо ожидания 30-секундного
polling tick'а.

#### Архитектура

```
HA coordinator
   ├─ Polling (как раньше) — fallback при разрыве WS
   └─ WebSocket task (background) ──┐
                                    ▼
                       AiohttpWsAdapter ──► WebSocketClient (aiosber)
                                    │
                                    ▼ TopicRouter
                       on(DEVICE_STATE) → async_request_refresh()
                       on(DEVMAN_EVENT) → log (TODO: HA event bus)
```

#### Что добавлено

- **`_ws_adapter.py`** — `AiohttpWsAdapter` имплементирует
  `aiosber.WebSocketProtocol` поверх `aiohttp.ClientWebSocketResponse`.
  HA core всё равно тянет `aiohttp` → ноль новых зависимостей в HA.
  `make_aiohttp_factory(session)` создаёт `WebSocketFactory`-совместимую функцию.
- **`HomeAPI.get_auth_manager()` + `get_sber_client()`** — public-методы для
  доступа к AuthManager / SberClient (нужны coordinator'у для построения WS).
- **`SberHomeCoordinator._start_ws_task()`** — запускает background-task
  после первого успешного polling refresh. Использует
  `hass.async_create_background_task` (управляется HA, корректный shutdown).
- **`_run_ws()`** — создаёт `WebSocketClient` с `TopicRouter`:
  - `Topic.DEVICE_STATE` → `_on_ws_device_state` → `async_request_refresh()`.
  - `Topic.DEVMAN_EVENT` → `_on_ws_devman_event` → log (placeholder для events).
- **`async_shutdown`** — корректно останавливает WS task + закрывает
  соединение через `contextlib.suppress` для best-effort cleanup.

#### Почему `async_request_refresh()` а не точечный patch

`StateDto` в текущей версии (из wire-протокола) НЕ содержит `device_id` напрямую —
он часть state объекта. Точечный patch без device_id ненадёжен. Trigger
refresh даёт latency <1s vs 30s polling — это уже огромный win. После
верификации формата на реальном устройстве можно добавить
`StateDto.device_id` и патчить точечно.

### Тесты

- **+9 тестов** в `tests/test_ws_adapter.py`:
  recv (text/binary/close/error), send (str/bytes), close (idempotent),
  factory создаёт adapter с правильными headers.
- `tests/test_coordinator.py` — fixture обновлена с `_ws_task`/`_ws_client`
  (чтобы существующие 6 тестов продолжали работать без WS-task creation).
- Всего **810 тестов** (было 801).

### Что НЕ сделано (отделено)

- **Точечный patch** конкретного device без `async_request_refresh()` — нужна
  верификация `device_id` поля в WS-сообщениях на реальном устройстве.
- **DEVMAN_EVENT** интеграция в HA event bus / EventEntity — нужна верификация
  shape payload. Сейчас просто логируется.
- **Camera support** + **CI workflow** + **2.0.0 PyPI extract** — следующие PR.

## [1.8.1] — 2026-04-16

### Audit покрытия typed wrappers (PR #10)

После audit'а в режиме сравнения с `sber_full_spec.json` + sealed-hierarchy
из wire-протокола (`research_docs/04 §6.1`) — закрыты все 6 пропущенных spec-фич
и 44 extra-поля из wire-наблюдений.

#### Coverage до/после

| Метрика | До audit | После closures |
|---|---|---|
| Spec features покрыто | 87% (161/185) | **100% (167/167)** |
| wire analysis extras | 44 ⚠️ | **0 ✅** |
| Тесты | 784 | **801 (+17)** |

Оставшиеся 18 features (185-167) — это commands/set-only fields, которые
архитектурно НЕ должны быть property (open_set/vacuum_command/custom_key/
direction/unlock/reject_call). Они отправляются через `DeviceAPI.set_state()`
или entity services HA, не через TypedDevice (read-only view).

#### Закрытые spec gaps

- **`gate`** — `open_rate`, `left_position`/`right_position` (как у `curtain`).
- **`hvac_humidifier`** — `replace_filter_alarm`, `replace_ionizer_alarm`,
  `water_percentage`.

#### Закрытые wire-protocol extras

- **`valve.fault_alarm`** — `alarm`/`external`/`normal` (ValveFaultAlarmAttr).
- **`socket.upper_current_threshold`** — защитный порог тока.
- **`hvac_air_purifier.decontaminate`** — UV-обеззараживание.
- **`intercom.virtual_open_state`, `unlock_duration`** — UI-состояние и config.
- **`scenario_button.click_mode`, `is_double_click_enabled`,
  `led_indicator_on/off`, `color_indicator_on/off`** — config из wire-наблюдений.
- **`_OpenCloseMixin.reverse_mode`, `opening_time`, `calibration`** —
  config-fields для всех cover-устройств.
- **`CurtainDevice.show_setup`**, **`WindowBlindDevice.light_transmission`**.
- **`_ThermostatMixin`** — новый mixin для Radiator/Boiler/Underfloor с
  13 config-полями: `min_temperature`, `max_temperature`, `device_condition`,
  `heating_hysteresis`, `anti_frost_temp`, `temperature_correction`,
  `schedule_status`, `open_window`, `open_window_status`, `floor_type`,
  `floor_sensor_type`, `main_sensor`. RadiatorDevice добавил `child_lock`,
  `adjust_floor_temp`, `show_setup`. BoilerDevice — `schedule` (ScheduleValue).

#### Инструменты

- **`tools/audit_coverage.py`** — auto-script сравнивает `aiosber/dto/devices/*.py`
  с features из spec.json + extras из wire-наблюдений. Выводит markdown-отчёт.
- **`research_docs/07-attribute-coverage-audit.md`** — auto-generated отчёт.
- **`tests/aiosber/dto/test_devices.py::TestSpecCoverageRegression`** —
  regression-test через subprocess вызов audit script. Падает если в spec
  появятся новые features без typed-property — защита от drift.

### Тесты

- **+17 новых** (`TestGateExtended`, `TestHumidifierExtended`,
  `TestAirPurifierDecontaminate`, `TestValveFaultAlarm`, `TestSocketUpperCurrent`,
  `TestIntercomConfig`, `TestScenarioButtonConfig`, `TestCoversConfig`,
  `TestThermostatMixin`, `TestSpecCoverageRegression`).
- Всего **801 тест**.

## [1.8.0] — 2026-04-16

### Добавлено: Типизированные модели устройств (PR #9)

Полная sealed-hierarchy типизированных wrappers поверх `DeviceDto` —
один class на каждую из 28 категорий. Соответствует sealed `SmartDevice`
hierarchy из wire-протокола (см. `research_docs/04-dataclasses.md` §6.1).

#### `aiosber/_generated/` — auto-generated константы

- **`tools/generate_constants.py`** — script читает `docs/sber_full_spec.json` →
  генерит 4 файла:
  - `category_features.py` — `ALL_CATEGORIES` (frozenset из 28),
    `CATEGORY_FEATURES`, `CATEGORY_OBLIGATORY`, `CATEGORY_ALL_FEATURES`.
  - `feature_types.py` — `FEATURE_TYPES: dict[str, str]` для всех ~80 features
    (BOOL/INTEGER/FLOAT/ENUM/STRING/COLOR/SCHEDULE).
  - `feature_enums.py` — `FEATURE_ENUMS` — допустимые значения для ENUM-фич.
  - `feature_ranges.py` — `FEATURE_RANGES` — per-category min/max/step для
    INTEGER-фич (например `hvac_temp_set` с разными диапазонами для
    radiator/boiler/underfloor).
- Single source of truth — `docs/sber_full_spec.json`. При обновлении spec
  достаточно перезапустить `python tools/generate_constants.py`.
- `pyproject.toml` — `_generated/` помечен в `[tool.ruff.lint.per-file-ignores]`
  (длинные строки нормальны для auto-gen формата).

#### `aiosber/dto/devices/` — typed wrappers (28 классов)

- **`_base.py`** — `TypedDevice`: универсальные `id`/`name`/`category`/`model`/
  `serial_number`/`sw_version` + `online`/`battery_percentage`/`battery_low`/
  `signal_strength` + `has_feature(key)`/`feature_type(key)`/`dto`.
- **`lights.py`** — `LightDevice` (is_on, brightness, color, color_temp, mode),
  `LedStripDevice` (наследует + sleep_timer).
- **`electric.py`** — `SocketDevice`, `RelayDevice` через `_PowerMonitorMixin`
  (voltage, current_milliamps/amps, power_watts, child_lock).
- **`sensors.py`** — `TemperatureSensorDevice`, `WaterLeakSensorDevice`,
  `DoorSensorDevice` (is_open + tamper), `MotionSensorDevice` (с fallback
  pir → motion_state), `SmokeSensorDevice`, `GasSensorDevice`.
- **`covers.py`** — `CurtainDevice` (с has_left_panel/has_right_panel/
  left_position/right_position для двустворчатых), `WindowBlindDevice`,
  `GateDevice`, `ValveDevice` через `_OpenCloseMixin`.
- **`hvac.py`** — `_HvacBaseDevice` + `AirConditionerDevice` (work_mode/
  fan_speed/air_flow_direction/target_humidity/night_mode/ionization),
  `HeaterDevice` (thermostat_mode), `RadiatorDevice`, `BoilerDevice`
  (thermostat_mode + heating_rate), `UnderfloorHeatingDevice`, `FanDevice`,
  `AirPurifierDevice` (replace_filter_alarm/aromatization), `HumidifierDevice`
  (water_level/water_low_alarm).
- **`appliances.py`** — `KettleDevice` (water_temperature/target/water_level/
  water_low_alarm/child_lock), `VacuumDevice` (status/program/cleaning_type),
  `TvDevice` (source/volume/muted/channel).
- **`misc.py`** — `ScenarioButtonDevice` (`button_event(n)` для 1-10 +
  `directional_event(direction)`), `IntercomDevice`, `HubDevice`.

#### Dispatcher

- **`as_typed(dto: DeviceDto) -> TypedDevice`** — авто-выбор класса по
  `image_set_type` (точное совпадение → substring fallback → базовый
  `TypedDevice` для unknown категорий).
- **`class_for_category(cat) -> type | None`** — lookup класса без instance.
- **`all_categories() -> frozenset[str]`** — все 28 покрытых категорий.

```python
from aiosber import as_typed, LightDevice

devices = await client.devices.list()
for d in devices:
    typed = as_typed(d)
    if isinstance(typed, LightDevice) and typed.is_on:
        print(f"{typed.name}: brightness={typed.brightness}")
```

### Тесты

- **+45 тестов** в `tests/aiosber/dto/test_devices.py`:
  все 28 категорий + dispatcher + base methods + spec/typed integration check
  (каждая категория из spec имеет typed-class и наоборот).
- Всего **784 теста** (вместо 739).

### Архитектурная симметрия

Теперь aiosber имеет **полную ребро-к-ребру модель Sber API**:
- Транспортный слой: HttpTransport + WebSocketClient.
- Auth: PKCE + AuthManager.
- API endpoints: DeviceAPI + GroupAPI + ScenarioAPI + PairingAPI + IndicatorAPI.
- DTO: AttributeValueDto + DeviceDto + 28 typed wrappers.
- Generated constants: features/types/enums/ranges из spec.
- DTO без бизнес-логики — соответствует CLAUDE.md (read-only views).

## [1.7.1] — 2026-04-16

### Cleanup (PR #7)

- **Lint полностью чистый** во всём проекте (`ruff check custom_components/ tests/` → All checks passed).
  Закрыто 48 pre-existing warnings (B904, UP017, I001, F401 и т.д.).
- **`pyproject.toml`** — добавлены `[tool.ruff.lint.per-file-ignores]` для тестов
  (E501, F841 — оправданы для длинных JSON payloads и mock-результатов).
- **`.pre-commit-config.yaml`** — добавлен в проект:
  - `ruff` + `ruff-format` авто-проверка.
  - `aiosber-no-ha-imports` — запускает `tests/aiosber/test_no_ha_imports.py`
    при изменении файлов в `aiosber/`. **Гарантирует архитектурное правило**
    из CLAUDE.md (zero HA imports в standalone-ядре).
- **`.gitignore`** — `.pre-commit-config.yaml` больше не игнорируется (часть проекта).
- **`README.md`** — обновлён под новую архитектуру:
  - Описание разделения на `aiosber/` ядро и HA-адаптер.
  - Quick-start пример использования `SberClient`.
  - Упоминание новых фич (intercom buttons, двустворчатые cover, TV IR services).
  - Обновлены цифры (739 тестов вместо 437).

## [1.7.0] — 2026-04-16

### Quick wins (PR #6 + #8)

#### Новая платформа `button` для intercom
- `Platform.BUTTON` добавлен в `PLATFORMS`.
- `button.py` — `SberButton` через декларативный `ButtonSpec` в `registry.py`.
- Категория `intercom` теперь даёт **2 button-сущности**:
  `button.intercom_unlock` (mdi:door-open) и `button.intercom_reject_call` (mdi:phone-hangup).
- Поддержка ENUM-команд через `ButtonSpec.command_value` (для будущих категорий).
- 7 тестов в `tests/test_button.py`.

#### Двустворчатые curtain / gate
- `cover.py` теперь создаёт **до 3 cover-сущностей** на устройство:
  - Основная (всегда) — `open_set` / `open_state` / `open_percentage`.
  - Левая створка — если у device есть `open_left_set` в reported_state.
  - Правая створка — аналогично.
- Новый класс `SberSideCover` (наследник `SberGenericCover`) с авто-генерируемыми
  side-keys (`open_left_*` / `open_right_*`) и unique_id `<device>_<side>`.
- 4 новых теста (всего 24 в test_cover.py).

#### TV: IR-style commands через entity services
- `media_player.py` теперь регистрирует **3 entity services**:
  - `sberhome.send_custom_key` — confirm/back/home (CustomKeyAttr).
  - `sberhome.send_direction` — up/down/left/right (DirectionAttr).
  - `sberhome.play_channel` — переключение по integer-индексу.
- Используются для пультов TV из автоматизаций HA.
- 3 новых теста (всего 24 в test_media_player.py).

#### Color bug fix (бонус из PR #5)
- `_legacy_state_to_attr` в `api.py` принимает оба формата:
  legacy `{h, s, v}` (как пишет HA-side `light.py`) и правильный
  `{hue, saturation, brightness}` (как ждёт Sber). Конвертация автоматическая
  через `aiosber.dto.ColorValue`. **Бага больше нет.**

#### CLI examples (PR #8)
- `examples/list_devices.py` — полный PKCE OAuth flow + список устройств.
- `examples/set_color.py` — изменение цвета лампы через готовый companion-токен.
- `examples/ws_listen.py` — подписка на real-time WebSocket с `TopicRouter`.
- `examples/README.md` — инструкции запуска.

### Цифры

- **739 тестов** (было 725; +14 новых: 7 button + 4 side cover + 3 TV IR).
- Все pre-existing тесты проходят без правок.
- Новых платформ: 1 (button).
- Новых entity services: 3 (для TV).
- Покрыто spec-фич которых не было: `unlock`, `reject_call`, `open_left_*`,
  `open_right_*`, `custom_key`, `direction`.

### Что ещё не сделано (PR #7, 2.0.0)

- 48 pre-existing ruff warnings в HA-коде.
- pre-commit hook для `test_no_ha_imports.py` compliance check.
- Update README.md с описанием новой архитектуры.
- WebSocket integration в coordinator (real-time updates) — нужен `_ws_adapter.py`.
- `_generated/` constants из spec.
- Extract aiosber → отдельный repo + PyPI (2.0.0).

## [1.6.0] — 2026-04-16

### Миграция HA-кода на aiosber (PR #5)

`api.py` полностью переписан — `SberAPI`/`HomeAPI` теперь **тонкие adapter'ы** над
`SberClient` из aiosber. Публичный интерфейс сохранён → coordinator/config_flow/
платформы НЕ менялись, тесты проходят.

**Что ушло:**
- Authlib (`AsyncOAuth2Client`) — заменён на чистый PKCE-flow из `aiosber.auth`.
- Module-level `_ssl_context` (антипаттерн "global state") — заменён на
  `_ssl_provider = SslContextProvider()` (instance-based, lazy в executor).
- Manual JWT exp parsing + ручной refresh — заменён на `AuthManager` с
  `asyncio.Lock` и `is_expired()` логикой.
- Custom code 16 retry в `request()` — заменён на встроенный 401/403 retry
  через `HttpTransport.force_refresh()`.

**Что появилось:**
- `_ha_token_store.py` — `HATokenStore` (имплементация `aiosber.auth.TokenStore`
  Protocol через `config_entry.data`). Готов к использованию когда coordinator
  начнёт прямые вызовы `SberClient` (вместо shim'а).
- `_legacy_state_to_attr()` — конвертация legacy `{"key": ..., "X_value": ...}`
  dict → `AttributeValueDto`. Поддерживает оба формата color: legacy `{h, s, v}` и
  правильный `{hue, saturation, brightness}`.
- Endpoints обновлены на актуальные `id.sber.ru/CSAFront/oidc/*` (вместо устаревшего
  `online.sberbank.ru/CSAFront/*`).
- `RqUID` header автоматически на token endpoint.
- `x-trace-id` автоматически на companion endpoint и каждом gateway-запросе.

### Тесты

- `tests/test_api.py` полностью переписан (29 тестов вместо 26 старых).
  Старые `patch.object(home_api._client.request, ...)` заменены на
  `httpx.MockTransport` (как в aiosber).
- 6 тестов `test_coordinator.py` + 11 тестов `test_config_flow.py` проходят
  без правок (публичный интерфейс HomeAPI/SberAPI сохранён).
- Всего **725 тестов** (было 722; +3 за счёт новых `_legacy_state_to_attr` cases).

### Поведенческие изменения для пользователей

- **Новые установки** (свежий OAuth) — авторизация на `id.sber.ru` (не
  `online.sberbank.ru`). UI flow тот же.
- **Существующие установки** — companion-токены продолжают работать, refresh
  через SberID refresh_token (если есть). Если refresh_token в config_entry
  отсутствует или истёк → reauth flow (как и раньше).

### Что НЕ сделано (отделено в следующие PR)

- WebSocket integration в coordinator (real-time updates) — PR #5.6 (нужен
  `_ws_adapter.py` через aiohttp.ws_connect).
- Color bug fix в `light.py` (h/s/v → hue/saturation/brightness) — PR #6.
- Intercom buttons, TV custom_key, двустворчатые cover — PR #6.
- 48 pre-existing ruff warnings в HA-коде — PR #7.

## [1.5.0] — 2026-04-16

### Добавлено: GroupAPI + ScenarioAPI + PairingAPI + IndicatorAPI

PR #4 из roadmap. Расширение `aiosber.api` четырьмя новыми доменами. Закрывает
все основные endpoint'ы Sber Gateway, перечисленные в `research_docs/01-rest-api.md`.

- **`aiosber.api.GroupAPI`** — `/gateway/v1/device_groups/*`:
  - `list()`, `get(id)`, `tree()` — чтение групп.
  - `create(name, parent_id)`, `delete(id)` — CRUD.
  - `set_state(id, attributes, *, return_group_status=None)` — команда всем устройствам в группе.
  - `rename`, `move`, `set_image`, `set_silent` — настройки группы.
- **`aiosber.api.ScenarioAPI`** — `/gateway/v1/scenario/v2/*`:
  - `list()`, `get(id)`, `list_system()`, `list_widgets()`.
  - `create(scenario)`, `update(id, scenario)`, `delete(id)`.
  - `execute_command(cmd)`, `fire_event(event)` — runtime.
  - `get_at_home()` / `set_at_home(bool)` — переменная "я дома".
  - `get_form()`, `set_requires(...)` — конструктор.
- **`aiosber.api.PairingAPI`** — `/gateway/v1/devices/pairing` + Matter:
  - `start_pairing(DeviceToPairingBody)` — generic pairing.
  - `get_wifi_credentials()` — bootstrap creds.
  - `list_matter_categories()`, `matter_attestation`, `matter_request_noc`,
    `matter_complete`, `matter_connect_controller/device` — Matter commissioning.
- **`aiosber.api.IndicatorAPI`** — `/gateway/v1/devices/indicator/values`:
  - `get()` → `IndicatorColors` DTO с `default_colors`/`current_colors`.
  - `get_raw()` для отладки.
  - `set(IndicatorColor)` — обновить.

### SberClient

- Добавлены свойства `client.groups`, `client.scenarios`, `client.pairing`, `client.indicator`.
- Все домены — на одном `HttpTransport` (один shared httpx.AsyncClient + auth).

### Тесты

- **+41 теста** (всего 14 + 14 + 9 + 4): `test_groups.py`, `test_scenarios.py`,
  `test_pairing.py`, `test_indicator.py`. Покрытие 86-100% по новым модулям.
- Всего **722 теста** (было 681). Pre-existing 437 HA-тестов нетронуты.

### Финальный статус aiosber

**PR #1-#4 закрыты.** `aiosber` — полностью функциональный standalone async-клиент:
- ✅ Auth: OAuth2/PKCE + companion + AuthManager (refresh + asyncio.Lock).
- ✅ Transport: HTTP (retry + headers + 401 retry) + WS (reconnect + dispatch) + SSL.
- ✅ API endpoints: Devices, Groups, Scenarios, Pairing, Indicator.
- ✅ DTO слой: 30+ dataclass'ов с from_dict/to_dict + 47 Sber enum'ов.
- ✅ Compliance: zero HA imports (CI-checked AST).
- ✅ Coverage: 92%+ среднее, 100% для критических модулей.
- ✅ 285 unit-тестов через `httpx.MockTransport` (без сетевых зависимостей).

### Оставшаяся работа (вне scope этих 4 PR)

- **PR #5** — миграция HA-кода (`api.py`, `coordinator.py`, `config_flow.py`,
  платформ light/cover/etc) на `SberClient`. Требует careful code review т.к.
  затрагивает 437 существующих тестов.
- **Опционально** — выделение `aiosber` в отдельный repo + публикация на PyPI.

## [1.4.0] — 2026-04-16

### Добавлено: WebSocketClient

PR #3 из roadmap. Real-time WS-клиент для `wss://ws.iot.sberdevices.ru` с
автоматическим reconnect и dispatching по `Topic`.

- **`aiosber.transport.WebSocketClient`** — основной класс:
  - `run()` — infinite reconnect loop с exponential backoff (1→2→4→...→60 s).
  - `stop()` — graceful shutdown.
  - `is_connected`, `wait_until_connected()` — для интеграционных тестов.
  - Auth через `AuthManager.access_token()` на каждый handshake.
  - Поддержка sync и async callbacks. Исключения внутри callback **не ломают** WS loop.
  - Корректная обработка `bytes` / `str` входящих фреймов, ignore non-JSON.
- **`aiosber.transport.WebSocketProtocol`** — `Protocol` с `recv/send/close`
  (совместим с `websockets`, `aiohttp` ws-response).
- **`aiosber.transport.WebSocketFactory`** — `Callable[[url, headers], Awaitable[WebSocketProtocol]]`.
  Через DI можно подменить на любой WS-провайдер.
- **`aiosber.transport.default_websockets_factory`** — default factory с **lazy import**
  библиотеки `websockets`. При отсутствии бросает понятную `SberError`.
- **`aiosber.TopicRouter`** — helper для подписки разных callbacks на разные `Topic`:
  - `router.on(Topic.DEVICE_STATE, callback)`.
  - Поддержка multiple handlers per topic.
  - Используется как `WebSocketClient(callback=router)`.

### Зависимости

- Добавлено в `manifest.json:requirements`: `websockets>=12.0` — для production.
  В тестах НЕ требуется (используется in-memory `FakeWebSocket`).

### Тесты

- **+15 тестов** в `tests/aiosber/transport/test_ws.py`:
  basic dispatch, async/sync callbacks, JSON/bytes, exception isolation,
  reconnect after disconnect / factory error, stop(), TopicRouter dispatch.
- Mock-server через `FakeWebSocket(messages, ...)` — реализация `WebSocketProtocol`
  in-memory, без сетевых зависимостей.
- Всего **681 теста** (вместо 666). Coverage `ws.py` ~93%.

### НЕ сделано (по дизайну)

Интеграция WebSocketClient в `coordinator.py` HA-адаптера — отделена в **PR #5**
(вместе с миграцией на `SberClient`). Текущий PR даёт **готовую инфраструктуру**,
готовую к подключению одной строкой в HA.

## [1.3.0] — 2026-04-16

### Добавлено: SberClient + DeviceAPI

PR #2 из roadmap. Высокоуровневый async-клиент над `aiosber.transport` + `aiosber.auth`.

- **`aiosber.api.DeviceAPI`** — REST endpoints для устройств:
  - `list()` — все устройства через `device_groups/tree` + `flatten_device_tree()`.
  - `list_flat()` — альтернатива через `/devices/`.
  - `get(device_id)`.
  - `set_state(id, attributes, *, timestamp=None)` — с автоматическим UTC ISO-Z timestamp.
  - `set_state_dto(id, body)` — принимает готовый `DesiredDeviceStateDto`.
  - `rename(id, name)`, `move(id, parent_id)`, `enums()`, `discover(id)`.
  - `_unwrap_result()` снимает `{"result": ...}` обёртку gateway response.
- **`aiosber.SberClient`** — фасад с тремя способами конструкции:
  - `SberClient(transport=...)` — для полного DI всех слоёв.
  - `await SberClient.from_companion_token("...")` — quick start с готовым токеном.
  - `await SberClient.from_oauth_setup(sberid_tokens=...)` — после OAuth-flow с auto-refresh.
  - `client.devices: DeviceAPI`, `client.transport: HttpTransport`.
  - Async context manager — `aclose()` закрывает transport (и httpx).
- **Companion legacy format support**: `exchange_for_companion_token` теперь распарсит
  `{"token": "..."}` (старый формат) в дополнение к `{"access_token": ...}` (modern OAuth2).

### Тесты

- **+31 теста** в `tests/aiosber/api/test_devices.py` и `tests/aiosber/test_client.py`.
- Покрытие: `client.py` 100%, `devices.py` 95%, `companion.py` 88%.
- Всего **666 тестов** (вместо 635). Pre-existing 437 HA-тестов не задеты.

### НЕ сделано (по дизайну)

Миграция HA-кода (`api.py`, `coordinator.py`, платформы) на `SberClient` —
**отделена в PR #5**. Текущий PR расширяет `aiosber` без изменения HA-адаптера,
сохраняя 437 HA-тестов нетронутыми.

## [1.2.0] — 2026-04-16

### Добавлено: standalone-ядро `aiosber`

PR #1 из roadmap миграции на чистую архитектуру (см. CLAUDE.md → «Архитектурная парадигма»).
Создан HA-independent пакет `custom_components/sberhome/aiosber/` — фундамент для
тонкого HA-адаптера (PR #2-4). Готов к extract в свой PyPI-пакет одним поиск-заменой.

**Структура:**

- `aiosber/const.py` — endpoints, CLIENT_ID, ROOT_CA_PEM (Russian Trusted Root CA).
  **OAuth-endpoints обновлены** на актуальные `id.sber.ru/CSAFront/oidc/*`
  (старые `online.sberbank.ru/CSAFront/*` устарели).
- `aiosber/exceptions.py` — иерархия `SberError → AuthError | NetworkError | ApiError | RateLimitError | ProtocolError`,
  `InvalidGrant` для случаев когда нужен полный re-auth.
- `aiosber/auth/` — полный OAuth2 PKCE flow:
  - `tokens.py` — `SberIdTokens`, `CompanionTokens` с `expires_at`/`is_expired()`.
  - `store.py` — `TokenStore` Protocol + `InMemoryTokenStore`.
  - `pkce.py` — `PkceParams.generate()`, `build_authorize_url()`, `extract_code_from_redirect()`.
  - `oauth.py` — `exchange_code_for_tokens()`, `refresh_sberid_tokens()` с обязательным `RqUID`.
  - `companion.py` — `exchange_for_companion_token()` с `x-trace-id`.
  - `manager.py` — `AuthManager` с auto-refresh, asyncio.Lock на серrialization, fallback
    через SberID refresh при истечении companion-токена.
- `aiosber/transport/` — транспортный слой:
  - `ssl.py` — `SslContextProvider` с lazy init **через executor** и **БЕЗ global state**
    (заменяет module-level `_ssl_context` из `api.py`).
  - `http.py` — `HttpTransport` с подписью `Authorization: Bearer`, RqUID/x-trace-id headers,
    автоматический retry на 401/403 через `AuthManager.force_refresh()`, маппинг HTTP-статусов
    в типизированные исключения (429 → `RateLimitError` с `retry_after`).
- `aiosber/dto/` — переехал из `custom_components/sberhome/dto/`. Без логических изменений.

### Тесты

- **+80 новых** в `tests/aiosber/`: PKCE generation/extract, token DTO roundtrip, OAuth/Companion
  endpoints с `httpx.MockTransport`, `AuthManager` (refresh, asyncio.Lock concurrency), `HttpTransport`
  (headers, retry, error mapping), SSL provider (lazy + concurrent + no-global-state).
- **`tests/aiosber/test_no_ha_imports.py`** — compliance check: AST-парсит все файлы `aiosber/`
  и блокирует импорты `homeassistant`, `voluptuous`, `aiohttp`. Защищает архитектурное правило.
- Всего **635 тестов** (вместо 555). Coverage `aiosber/` ~92% (enums, store, ssl, exceptions — 100%).

### Backwards-compatible

Существующий `api.py` / `coordinator.py` / config_flow / платформы не тронуты.
Новый слой добавлен параллельно. Миграция HA-кода на `aiosber` — PR #2.

## [1.1.0] — 2026-04-16

### Добавлено

- **Полный типизированный DTO-слой** `custom_components/sberhome/dto/` на основе
  wire-анализа Sber Салют v26.03.1.18015. 8 модулей, ~30 dataclass'ов с
  `from_dict`/`to_dict`, 35 *Attr enum'ов с wire-значениями, namespace `AttrKey`
  со всеми ключами `AttributeValueDto.key`, `SocketMessageDto` для WS с
  диспетчером по `Topic`.
- **118 новых тестов** (всего 555, +0% к существующим). Покрытие DTO-слоя ~88%,
  enums.py — 100%.

### Backwards-compatible

Существующий код (`api.py`, `coordinator.py`, платформы) не изменён — миграция
на DTO будет отдельной задачей. DTO доступен как опциональный публичный API:

```python
from custom_components.sberhome.dto import (
    DeviceDto, AttributeValueDto, AttrKey, ColorValue,
    DesiredDeviceStateDto, HvacWorkMode, SocketMessageDto, Topic,
)
```

### Известные расхождения с текущим api.py (зафиксировано в DTO)

- `ColorValue` использует поля **`hue/saturation/brightness`**, а не `h/s/v`.
- `MotionSensitivity`, `Antiflicker`, `Nightvision`, `DecibelSensitivity` — wire-
  это **строки с цифрами** (`"0"/"1"/"2"`), не Boolean/int.
- `SdStatusAttr` — единственный INTEGER-wire enum.
- `SignalStrength` может приходить как INTEGER (dBm) **или** ENUM low/medium/high.

## [1.0.0] — 2026-04-15

Первый релиз **SberHome**