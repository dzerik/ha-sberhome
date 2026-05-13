# SberHome — Справочник по сущностям и автоматизациям

> Версия интеграции: **5.7.1**
> Этот документ — справочник для уже установившего интеграцию. Установка, авторизация, благодарности, лицензия — в [README.md](README.md).

---

## Содержание

1. [Введение](#введение)
2. [Поддерживаемые платформы](#поддерживаемые-платформы)
3. [Справочник сущностей по категориям](#справочник-сущностей-по-категориям)
   - [Освещение (light, led_strip)](#освещение-light-led_strip)
   - [Розетки и реле (socket, relay)](#розетки-и-реле-socket-relay)
   - [Чайники (kettle)](#чайники-kettle)
   - [Датчики климата (sensor_temp)](#датчики-климата-sensor_temp)
   - [Датчики протечки (sensor_water_leak)](#датчики-протечки-sensor_water_leak)
   - [Датчики открытия (sensor_door)](#датчики-открытия-sensor_door)
   - [Датчики движения (sensor_pir)](#датчики-движения-sensor_pir)
   - [Датчики дыма (sensor_smoke)](#датчики-дыма-sensor_smoke)
   - [Датчики газа (sensor_gas)](#датчики-газа-sensor_gas)
   - [Шторы, жалюзи, ворота, клапаны (cover)](#шторы-жалюзи-ворота-клапаны-cover)
   - [Кондиционеры и обогреватели (climate)](#кондиционеры-и-обогреватели-climate)
   - [Вентиляторы и очистители воздуха (fan)](#вентиляторы-и-очистители-воздуха-fan)
   - [Увлажнители (hvac_humidifier)](#увлажнители-hvac_humidifier)
   - [Телевизоры (tv)](#телевизоры-tv)
   - [Роботы-пылесосы (vacuum_cleaner)](#роботы-пылесосы-vacuum_cleaner)
   - [Сценарные выключатели (scenario_button)](#сценарные-выключатели-scenario_button)
   - [Домофоны (intercom)](#домофоны-intercom)
   - [Хабы (hub)](#хабы-hub)
   - [Колонки Sber (sber_speaker)](#колонки-sber-sber_speaker)
4. [Специальные сущности](#специальные-сущности)
   - [Sber-сценарии как кнопки HA](#sber-сценарии-как-кнопки-ha)
   - [Присутствие дома (at_home)](#присутствие-дома-at_home)
   - [LED-индикатор колонок](#led-индикатор-колонок)
   - [Обновления прошивок (update)](#обновления-прошивок-update)
   - [Sber-группы как switch (v5.4.0+)](#sber-группы-как-switch-v540)
   - [TTS-уведомления (notify, v5.6.0+)](#tts-уведомления-notify-v560)
5. [HA events — sberhome_intent](#ha-events--sberhome_intent)
6. [YAML-конфигурация](#yaml-конфигурация)
   - [sberhome.intents (v5.2.0+)](#sberHomeintents-v520)
   - [sberhome.listeners (v5.5.0+)](#sberhomelisteners-v550)
7. [Сервисы HA](#сервисы-ha)
8. [Кастомная панель в сайдбаре](#кастомная-панель-в-сайдбаре)
9. [Multi-home](#multi-home)
10. [Световые эффекты (v5.4.0+)](#световые-эффекты-v540)
11. [TTS surrogate — подробно](#tts-surrogate--подробно)

---

## Введение

После установки и авторизации интеграция подтягивает из Sber Gateway все устройства, привязанные к вашему аккаунту. Устройства **не появляются в HA автоматически** — вы выбираете нужные в панели SberHome (сайдбар → SberHome → таб **Devices**).

Как найти сущности в HA:

- **Настройки → Устройства и службы → SberHome** — полный список устройств.
- **Панель SberHome** (кнопка в сайдбаре) — собственный UI интеграции с поиском, фильтром по категории, диагностикой и DevTools.
- Имена `entity_id` строятся по шаблону `<platform>.sberhome_<slug_имени_устройства>`.

Обновление состояний:

- Основной канал — **WebSocket push** (`wss://ws.iot.sberdevices.ru`). Изменение в Sber-устройстве приходит в HA обычно менее чем за 2 секунды.
- Резервный канал — **REST polling** (по умолчанию каждые 30 секунд; пока WS активен — раз в 10 минут только для discovery новых устройств).
- Интервал polling настраивается: Настройки → Устройства и службы → SberHome → **Настроить** (10–300 секунд).

---

## Поддерживаемые платформы

| HA Platform | Когда создаётся | Примерный entity_id |
|---|---|---|
| `binary_sensor` | Датчики (протечка, движение, дверь, дым, газ), online-состояние хаба/колонки | `binary_sensor.sberhome_datchik_dveri_door` |
| `button` | Sber-сценарии (облачные кнопки), кнопки домофона (unlock, reject_call) | `button.sberhome_scenarios_ukhod_iz_doma` |
| `climate` | Кондиционеры, обогреватели, радиаторы, бойлеры, тёплый пол | `climate.sberhome_konditsioner_gostinaya` |
| `cover` | Шторы, жалюзи, ворота, клапаны | `cover.sberhome_shtory_zal` |
| `event` | Сценарные выключатели (физические и виртуальные кнопки Sber) | `event.sberhome_vyklyuchatel_button_1_event` |
| `fan` | Вентиляторы (hvac_fan), очистители воздуха (hvac_air_purifier) | `fan.sberhome_ochistitel_vozdukha` |
| `humidifier` | Увлажнители (hvac_humidifier) | `humidifier.sberhome_uvlazhnytel` |
| `light` | Умные лампы, LED-ленты, LED-индикатор колонок | `light.sberhome_lampa_spalni`, `light.sber_indicator_color` |
| `media_player` | Телевизоры (tv) | `media_player.sberhome_televizor_zal` |
| `notify` | TTS surrogate — произношение через колонки Sber (experimental) | `notify.sberhome_moy_dom` |
| `number` | Числовые параметры (целевая температура чайника, таймер LED-ленты, влажность, светопропускание) | `number.sberhome_chaiynik_temperature_set` |
| `select` | Выбор режима (скорость вентилятора, направление потока, программа пылесоса и т.п.) | `select.sberhome_konditsioner_air_flow_direction` |
| `sensor` | Измеряемые величины (температура, влажность, давление, напряжение, ток, мощность, уровень воды, батарея, сигнал) | `sensor.sberhome_datchik_temperatura` |
| `switch` | Розетки, реле, Sber-группы устройств, child_lock, alarm_mute, ночной режим климата, ионизация | `switch.sberhome_rozetka_kuhnya` |
| `update` | Доступность обновлений прошивки (отключено по умолчанию) | `update.sberhome_lampa_spalni_firmware` |
| `vacuum` | Роботы-пылесосы | `vacuum.sberhome_pylesos` |

---

## Справочник сущностей по категориям

### Освещение (light, led_strip)

**Primary entity:** `light.<name>`

Поддерживаемые функции зависят от конкретной лампы:

| Функция | HA-атрибут | Условие появления |
|---|---|---|
| Вкл/выкл | `state` | Всегда |
| Яркость | `brightness` | Если устройство поддерживает `light_brightness` |
| Цвет (HS) | `hs_color` | Если поддерживает `light_colour` |
| Цветовая температура | `color_temp_kelvin` | Если поддерживает `light_colour_temp` |
| Световые эффекты (сцены) | `effect`, `effect_list` | Если в firmware есть `light_mode=scene` |

**Дополнительные сущности LED-ленты (led_strip):**

| Entity | Платформа | Описание |
|---|---|---|
| `number.<name>_sleep_timer` | `number` | Таймер автовыключения, 0–720 минут |

**Диагностические сущности (общие для всех устройств):**

| Entity | Платформа | Описание |
|---|---|---|
| `sensor.<name>_battery_percentage` | `sensor` | Заряд батареи, % |
| `sensor.<name>_signal_strength` | `sensor` | Уровень сигнала (low/medium/high или dBm) |
| `binary_sensor.<name>_battery_low_power` | `binary_sensor` | Низкий заряд батареи |
| `binary_sensor.<name>_online` | `binary_sensor` | Подключено к сети (DIAGNOSTIC) |
| `update.<name>_firmware` | `update` | Обновление прошивки (отключено по умолчанию) |

**Пример автоматизации — включить ночной режим подсветки:**

```yaml
automation:
  - alias: "Ночная подсветка в коридоре"
    trigger:
      - platform: time
        at: "22:00:00"
    action:
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lampa_koridor
        data:
          brightness_pct: 15
          color_temp_kelvin: 2700
```

**Пример автоматизации — световой будильник:**

```yaml
automation:
  - alias: "Световой будильник"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lampa_spalnya
        data:
          brightness_pct: 1
          color_temp_kelvin: 2700
      - delay: "00:10:00"
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lampa_spalnya
        data:
          brightness_pct: 100
          color_temp_kelvin: 6500
          transition: 600
```

---

### Розетки и реле (socket, relay)

**Primary entity:** `switch.<name>`

**Дополнительные сущности:**

| Entity | Платформа | Описание |
|---|---|---|
| `sensor.<name>_cur_voltage` / `_voltage` | `sensor` | Напряжение, В |
| `sensor.<name>_cur_current` / `_current` | `sensor` | Ток, А |
| `sensor.<name>_cur_power` / `_power` | `sensor` | Мощность, Вт |
| `switch.<name>_child_lock` | `switch` (CONFIG) | Защита от детей |

**Пример автоматизации — защитное отключение по мощности:**

```yaml
automation:
  - alias: "Отключить при перегрузке"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sberhome_rozetka_kuhnya_cur_power
        above: 2500
        for: "00:00:30"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.sberhome_rozetka_kuhnya
      - service: notify.persistent_notification
        data:
          message: "Розетка кухни отключена — превышение мощности (>2500 Вт)"
          title: "SberHome — предупреждение"
```

**Пример автоматизации — контроль потребления:**

```yaml
automation:
  - alias: "Уведомление: стиральная машина завершила работу"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sberhome_rozetka_stiralka_cur_power
        below: 10
        for: "00:02:00"
    condition:
      - condition: numeric_state
        entity_id: sensor.sberhome_rozetka_stiralka_cur_power
        above: 0
    action:
      - service: notify.mobile_app
        data:
          message: "Стирка завершена"
```

---

### Чайники (kettle)

**Primary entity:** `switch.<name>`

**Дополнительные сущности:**

| Entity | Платформа | Описание |
|---|---|---|
| `number.<name>_kitchen_water_temperature_set` | `number` | Целевая температура, 60–100 °C с шагом 10 |
| `sensor.<name>_kitchen_water_temperature` | `sensor` | Текущая температура воды, °C |
| `sensor.<name>_kitchen_water_level` | `sensor` | Уровень воды, % |
| `binary_sensor.<name>_kitchen_water_low_level` | `binary_sensor` | Низкий уровень воды (PROBLEM) |
| `switch.<name>_child_lock` | `switch` (CONFIG) | Защита от детей |

**Пример автоматизации — утренний сценарий:**

```yaml
automation:
  - alias: "Вскипятить чайник перед подъёмом"
    trigger:
      - platform: time
        at: "06:55:00"
    condition:
      - condition: time
        weekday:
          - mon
          - tue
          - wed
          - thu
          - fri
    action:
      - service: number.set_value
        target:
          entity_id: number.sberhome_chaiynik_kitchen_water_temperature_set
        data:
          value: 100
      - service: switch.turn_on
        target:
          entity_id: switch.sberhome_chaiynik
```

---

### Датчики климата (sensor_temp)

**Primary entity:** нет единой primary — все сущности создаются как extras.

| Entity | Платформа | Описание |
|---|---|---|
| `sensor.<name>_temperature` | `sensor` | Температура, °C |
| `sensor.<name>_humidity` | `sensor` | Влажность, % |
| `sensor.<name>_air_pressure` | `sensor` | Давление, гПа |
| `select.<name>_sensor_sensitive` | `select` (CONFIG) | Чувствительность (auto/high) |
| `select.<name>_temp_unit_view` | `select` (CONFIG) | Единица отображения (celsius/fahrenheit) |

**Пример автоматизации — контроль микроклимата:**

```yaml
automation:
  - alias: "Уведомление о высокой температуре"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sberhome_datchik_temperatura_gostinaya
        above: 28
    action:
      - service: notify.persistent_notification
        data:
          message: >
            Температура в гостиной {{ states('sensor.sberhome_datchik_temperatura_gostinaya') }} °C.
            Рекомендую включить кондиционер.
          title: "Жарко!"
```

**Пример автоматизации — автозапуск увлажнителя:**

```yaml
automation:
  - alias: "Включить увлажнитель при низкой влажности"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sberhome_datchik_temperatura_spalnya_humidity
        below: 40
        for: "00:15:00"
    action:
      - service: humidifier.turn_on
        target:
          entity_id: humidifier.sberhome_uvlazhnytel_spalnya
```

---

### Датчики протечки (sensor_water_leak)

**Primary entity:** `binary_sensor.<name>` (device_class: `moisture`)

| Entity | Платформа | Описание |
|---|---|---|
| `binary_sensor.<name>` | `binary_sensor` | Обнаружена вода (on = протечка) |

**Пример автоматизации — аварийное перекрытие воды:**

```yaml
automation:
  - alias: "Авария: закрыть клапан при протечке"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_protechki_kuhnya
        to: "on"
    action:
      - service: cover.close_cover
        target:
          entity_id: cover.sberhome_klapan_voda
      - service: notify.mobile_app
        data:
          message: "ВНИМАНИЕ! Обнаружена протечка на кухне. Клапан закрыт."
          title: "Протечка!"
```

---

### Датчики открытия (sensor_door)

**Primary entity:** `binary_sensor.<name>` (device_class: `door`)

| Entity | Платформа | Описание |
|---|---|---|
| `binary_sensor.<name>` | `binary_sensor` | Открыто/закрыто (on = открыто) |
| `binary_sensor.<name>_tamper_alarm` | `binary_sensor` (DIAGNOSTIC) | Вскрытие корпуса (tamper) |
| `select.<name>_sensor_sensitive` | `select` (CONFIG) | Чувствительность (auto/high) |

**Пример автоматизации — уведомление при открытии:**

```yaml
automation:
  - alias: "Уведомление: открыта входная дверь"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_dveri_vkhod
        to: "on"
    condition:
      - condition: state
        entity_id: binary_sensor.sber_at_home
        state: "off"
    action:
      - service: notify.mobile_app
        data:
          message: "Входная дверь открылась, но вас нет дома"
          title: "Безопасность"
```

---

### Датчики движения (sensor_pir)

**Primary entity:** `binary_sensor.<name>` (device_class: `motion`)

| Entity | Платформа | Описание |
|---|---|---|
| `binary_sensor.<name>` | `binary_sensor` | Обнаружено движение (on = есть движение) |
| `select.<name>_sensor_sensitive` | `select` (CONFIG) | Чувствительность (auto/high) |

**Пример автоматизации — свет по датчику движения:**

```yaml
automation:
  - alias: "Свет в коридоре по движению"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_dvizheniya_koridor
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lampa_koridor
        data:
          brightness_pct: 80

  - alias: "Выключить свет в коридоре после простоя"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_dvizheniya_koridor
        to: "off"
        for: "00:05:00"
    action:
      - service: light.turn_off
        target:
          entity_id: light.sberhome_lampa_koridor
```

---

### Датчики дыма (sensor_smoke)

**Primary entity:** `binary_sensor.<name>` (device_class: `smoke`)

| Entity | Платформа | Описание |
|---|---|---|
| `binary_sensor.<name>` | `binary_sensor` | Обнаружен дым (on = тревога) |
| `switch.<name>_alarm_mute` | `switch` (CONFIG) | Заглушить сигнализацию |

**Пример автоматизации — противопожарная сигнализация:**

```yaml
automation:
  - alias: "Пожарная тревога"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_dyma_kuhnya
        to: "on"
    action:
      - service: light.turn_on
        target:
          area_id: all
        data:
          hs_color: [0, 100]
          brightness: 255
      - service: notify.mobile_app
        data:
          message: "ПОЖАРНАЯ ТРЕВОГА! Обнаружен дым на кухне!"
          title: "ТРЕВОГА"
          data:
            priority: high
```

---

### Датчики газа (sensor_gas)

**Primary entity:** `binary_sensor.<name>` (device_class: `gas`)

| Entity | Платформа | Описание |
|---|---|---|
| `binary_sensor.<name>` | `binary_sensor` | Обнаружена утечка газа (on = тревога) |
| `switch.<name>_alarm_mute` | `switch` (CONFIG) | Заглушить сигнализацию |
| `select.<name>_sensor_sensitive` | `select` (CONFIG) | Чувствительность |

---

### Шторы, жалюзи, ворота, клапаны (cover)

**Primary entity:** `cover.<name>`

| Категория Sber | HA device_class |
|---|---|
| `curtain` | `curtain` |
| `window_blind` | `blind` |
| `gate` | `gate` |
| `valve` | — (без device_class) |

**Поддерживаемые операции:**

| Сервис HA | Описание |
|---|---|
| `cover.open_cover` | Открыть |
| `cover.close_cover` | Закрыть |
| `cover.set_cover_position` | Установить позицию (0–100%) |
| `cover.stop_cover` | Остановить |

**HA-атрибуты:**

| Атрибут | Описание |
|---|---|
| `current_position` | Текущая позиция, 0–100% |
| `state` | `open` / `closed` / `opening` / `closing` |

**Двустворчатые шторы** — для двустворчатых моделей создаются отдельные сущности `cover.<name>_left` и `cover.<name>_right`.

**Дополнительные сущности (жалюзи, шторы, ворота):**

| Entity | Платформа | Описание |
|---|---|
| `select.<name>_open_rate` | `select` (CONFIG) | Скорость открытия (auto/low/high) |

**Для window_blind дополнительно:**

| Entity | Платформа | Описание |
|---|---|
| `number.<name>_light_transmission_percentage` | `number` | Светопропускаемость, 0–100% |

**Пример автоматизации — шторы по времени:**

```yaml
automation:
  - alias: "Открыть шторы утром"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: cover.set_cover_position
        target:
          entity_id: cover.sberhome_shtory_spalnya
        data:
          position: 80

  - alias: "Закрыть шторы на закате"
    trigger:
      - platform: sun
        event: sunset
        offset: "-00:30:00"
    action:
      - service: cover.close_cover
        target:
          entity_id: cover.sberhome_shtory_spalnya
```

---

### Кондиционеры и обогреватели (climate)

Категории: `hvac_ac`, `hvac_heater`, `hvac_radiator`, `hvac_boiler`, `hvac_underfloor_heating`

**Primary entity:** `climate.<name>`

**Поддерживаемые HVAC-режимы (зависит от модели):**

| HVAC mode | Описание |
|---|---|
| `off` | Выключен |
| `cool` | Охлаждение |
| `heat` | Нагрев |
| `dry` | Осушение |
| `fan_only` | Только вентилятор |
| `auto` | Авто |

**HA-атрибуты:**

| Атрибут | Описание |
|---|---|
| `temperature` | Целевая температура, °C |
| `current_temperature` | Текущая температура, °C |
| `fan_mode` | Скорость вентилятора |

**Дополнительные сущности (для hvac_ac):**

| Entity | Платформа | Описание |
|---|---|
| `select.<name>_hvac_air_flow_direction` | `select` | Направление потока (auto/top/middle/bottom) |
| `number.<name>_hvac_humidity_set` | `number` | Целевая влажность, 30–80% |
| `switch.<name>_hvac_night_mode` | `switch` (CONFIG) | Ночной режим |
| `switch.<name>_hvac_ionization` | `switch` (CONFIG) | Ионизация |

**Для hvac_heater, hvac_boiler, hvac_underfloor_heating:**

| Entity | Платформа | Описание |
|---|---|
| `select.<name>_hvac_thermostat_mode` | `select` | Режим термостата (auto/eco/comfort/boost) |
| `select.<name>_hvac_heating_rate` | `select` (CONFIG) | Скорость нагрева (slow/medium/fast) |

**Пример автоматизации — программируемый обогрев:**

```yaml
automation:
  - alias: "Включить обогрев перед приходом домой"
    trigger:
      - platform: time
        at: "17:30:00"
    condition:
      - condition: time
        weekday: [mon, tue, wed, thu, fri]
    action:
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.sberhome_konditsioner_gostinaya
        data:
          hvac_mode: heat
      - service: climate.set_temperature
        target:
          entity_id: climate.sberhome_konditsioner_gostinaya
        data:
          temperature: 22

  - alias: "Выключить климат в режиме ночного сна"
    trigger:
      - platform: time
        at: "23:30:00"
    action:
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.sberhome_konditsioner_gostinaya
        data:
          hvac_mode: "off"
```

---

### Вентиляторы и очистители воздуха (fan)

Категории: `hvac_fan`, `hvac_air_purifier`

**Primary entity:** `fan.<name>`

**Поддерживаемые операции:** `fan.turn_on`, `fan.turn_off`, `fan.set_preset_mode`

**Preset modes:**

| Категория | Доступные режимы |
|---|---|
| `hvac_fan` | `low`, `medium`, `high`, `turbo` |
| `hvac_air_purifier` | `auto`, `low`, `medium`, `high`, `turbo` |

**Дополнительные сущности для hvac_fan:**

| Entity | Платформа | Описание |
|---|---|
| `select.<name>_hvac_direction_set` | `select` | Направление потока (auto/top/middle/bottom/swing) |

**Дополнительные сущности для hvac_air_purifier:**

| Entity | Платформа | Описание |
|---|---|
| `switch.<name>_hvac_night_mode` | `switch` (CONFIG) | Ночной режим |
| `switch.<name>_hvac_ionization` | `switch` (CONFIG) | Ионизация |
| `switch.<name>_hvac_aromatization` | `switch` (CONFIG) | Ароматизация |
| `switch.<name>_hvac_decontaminate` | `switch` (CONFIG) | Обеззараживание |
| `binary_sensor.<name>_hvac_replace_filter` | `binary_sensor` (DIAGNOSTIC) | Требуется замена фильтра |
| `binary_sensor.<name>_hvac_replace_ionizator` | `binary_sensor` (DIAGNOSTIC) | Требуется замена ионизатора |

**Пример автоматизации — включить очиститель при плохом воздухе:**

```yaml
automation:
  - alias: "Включить очиститель при высокой влажности"
    trigger:
      - platform: numeric_state
        entity_id: sensor.sberhome_datchik_spalnya_humidity
        above: 70
        for: "00:30:00"
    action:
      - service: fan.turn_on
        target:
          entity_id: fan.sberhome_ochistitel_vozdukha_spalnya
      - service: fan.set_preset_mode
        target:
          entity_id: fan.sberhome_ochistitel_vozdukha_spalnya
        data:
          preset_mode: "high"
```

---

### Увлажнители (hvac_humidifier)

**Primary entity:** `humidifier.<name>`

**Поддерживаемые операции:** `humidifier.turn_on`, `humidifier.turn_off`, `humidifier.set_humidity`, `humidifier.set_mode`

**HA-атрибуты:**

| Атрибут | Описание |
|---|---|
| `humidity` | Целевая влажность, % |
| `current_humidity` | Текущая влажность, % |
| `mode` | Текущий режим |

**Доступные режимы:** `auto`, `low`, `medium`, `high`, `turbo`

**Диапазон влажности:** 30–80% (шаг 5%)

**Дополнительные сущности:**

| Entity | Платформа | Описание |
|---|---|
| `switch.<name>_hvac_night_mode` | `switch` (CONFIG) | Ночной режим |
| `switch.<name>_hvac_ionization` | `switch` (CONFIG) | Ионизация |
| `sensor.<name>_hvac_water_level` | `sensor` | Уровень воды в резервуаре, % |
| `sensor.<name>_hvac_water_percentage` | `sensor` | Уровень воды, % |
| `binary_sensor.<name>_hvac_water_low_level` | `binary_sensor` | Низкий уровень воды (PROBLEM) |
| `binary_sensor.<name>_hvac_replace_filter` | `binary_sensor` (DIAGNOSTIC) | Требуется замена фильтра |
| `binary_sensor.<name>_hvac_replace_ionizator` | `binary_sensor` (DIAGNOSTIC) | Требуется замена ионизатора |

---

### Телевизоры (tv)

**Primary entity:** `media_player.<name>`

**HA-атрибуты:**

| Атрибут | Описание |
|---|---|
| `state` | `on` / `off` |
| `volume_level` | Уровень громкости, 0.0–1.0 |
| `is_volume_muted` | Флаг отключения звука |
| `source` | Текущий источник |

**Стандартные сервисы HA:**

| Сервис | Описание |
|---|---|
| `media_player.turn_on` / `turn_off` | Вкл/выкл |
| `media_player.set_volume_level` | Установить громкость (0.0–1.0) |
| `media_player.volume_up` / `volume_down` | Изменить громкость на шаг |
| `media_player.mute_volume` | Отключить/включить звук |
| `media_player.select_source` | Переключить источник |

**Дополнительные сервисы интеграции:**

| Сервис | Поля | Описание |
|---|---|---|
| `sberhome.send_custom_key` | `key`: `confirm` / `back` / `home` | Нажатие системной кнопки |
| `sberhome.send_direction` | `direction`: `up` / `down` / `left` / `right` | D-pad навигация |
| `sberhome.play_channel` | `channel`: 1–999 | Переключить на канал |

**Пример автоматизации — выключить ТВ по расписанию:**

```yaml
automation:
  - alias: "Выключить ТВ в полночь"
    trigger:
      - platform: time
        at: "00:00:00"
    condition:
      - condition: state
        entity_id: media_player.sberhome_televizor_gostinaya
        state: "on"
    action:
      - service: media_player.turn_off
        target:
          entity_id: media_player.sberhome_televizor_gostinaya
```

**Пример использования кастомного сервиса:**

```yaml
action:
  - service: sberhome.send_custom_key
    target:
      entity_id: media_player.sberhome_televizor_gostinaya
    data:
      key: "home"
```

---

### Роботы-пылесосы (vacuum_cleaner)

**Primary entity:** `vacuum.<name>`

**Поддерживаемые операции:**

| Сервис HA | Описание |
|---|---|
| `vacuum.start` | Начать уборку |
| `vacuum.pause` | Пауза |
| `vacuum.stop` | Остановить |
| `vacuum.return_to_base` | Вернуться на базу |
| `vacuum.locate` | Издать звуковой сигнал |

**HA-атрибуты:**

| Атрибут | Описание |
|---|---|
| `battery_level` | Заряд батареи, % |
| `activity` | Текущая активность (`cleaning`, `paused`, `returning`, `docked`, `idle`, `error`) |

**Дополнительные сущности:**

| Entity | Платформа | Описание |
|---|---|
| `select.<name>_vacuum_cleaner_program` | `select` | Программа уборки (perimeter/spot/smart) |
| `select.<name>_vacuum_cleaner_cleaning_type` | `select` | Тип уборки (dry/wet/mixed) |
| `switch.<name>_child_lock` | `switch` (CONFIG) | Защита от детей |

**Пример автоматизации — уборка в отсутствие:**

```yaml
automation:
  - alias: "Запустить пылесос когда ушли из дома"
    trigger:
      - platform: state
        entity_id: binary_sensor.sber_at_home
        to: "off"
        for: "00:10:00"
    condition:
      - condition: time
        after: "10:00:00"
        before: "18:00:00"
    action:
      - service: vacuum.start
        target:
          entity_id: vacuum.sberhome_pylesos

  - alias: "Вернуть пылесос при приходе домой"
    trigger:
      - platform: state
        entity_id: binary_sensor.sber_at_home
        to: "on"
    condition:
      - condition: state
        entity_id: vacuum.sberhome_pylesos
        state: "cleaning"
    action:
      - service: vacuum.return_to_base
        target:
          entity_id: vacuum.sberhome_pylesos
```

---

### Сценарные выключатели (scenario_button)

Физические и виртуальные кнопки Sber (включая c2c-кнопки типа «Эмуляция присутствия»).

**Primary entity:** нет единой primary.

**Создаваемые event-сущности:**

Для однокнопочных выключателей: `event.<name>_button_event`

Для многокнопочных — по одной entity на кнопку:

- `event.<name>_button_1_event`, `event.<name>_button_2_event`, ..., вплоть до `event.<name>_button_10_event`

Для выключателей с направленными кнопками:

- `event.<name>_button_left_event`, `event.<name>_button_right_event`
- `event.<name>_button_top_left_event`, `event.<name>_button_top_right_event`
- `event.<name>_button_bottom_left_event`, `event.<name>_button_bottom_right_event`

**Типы событий для каждой кнопки:**

| Тип события | Описание |
|---|---|
| `click` | Одиночное нажатие |
| `double_click` | Двойное нажатие |
| `long_press` | Долгое нажатие |

**Пример автоматизации — управление светом с кнопки:**

```yaml
automation:
  - alias: "Кнопка 1: включить свет"
    trigger:
      - platform: event
        event_type: state_changed
        event_data:
          entity_id: event.sberhome_vyklyuchatel_button_1_event
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.new_state.attributes.event_type == 'click' }}"
    action:
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lampa_gostinaya

  - alias: "Кнопка 1: двойной клик — выключить весь свет"
    trigger:
      - platform: event
        event_type: state_changed
        event_data:
          entity_id: event.sberhome_vyklyuchatel_button_1_event
    condition:
      - condition: template
        value_template: "{{ trigger.event.data.new_state.attributes.event_type == 'double_click' }}"
    action:
      - service: light.turn_off
        target:
          area_id: all
```

---

### Домофоны (intercom)

**Primary entity:** `binary_sensor.<name>` (обнаружение звонка / входящий вызов)

**Дополнительные сущности:**

| Entity | Платформа | Описание |
|---|---|
| `binary_sensor.<name>_incoming_call` | `binary_sensor` | Входящий вызов (on = звонок) |
| `button.<name>_unlock` | `button` | Открыть дверь |
| `button.<name>_reject_call` | `button` | Отклонить вызов |

**Пример автоматизации — автоматическое открытие двери:**

```yaml
automation:
  - alias: "Открыть дверь по команде"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          name: "Открыть дверь"
    action:
      - service: button.press
        target:
          entity_id: button.sberhome_domofon_unlock

  - alias: "Уведомление о звонке в дверь"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_domofon_incoming_call
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          message: "Звонок в дверь"
          title: "Домофон"
```

---

### Хабы (hub)

**Primary entity:** `binary_sensor.<name>` (device_class: `connectivity`)

**Дополнительные сущности:**

| Entity | Платформа | Описание |
|---|---|
| `binary_sensor.<name>_online` | `binary_sensor` (DIAGNOSTIC) | Подключение к сети |
| `binary_sensor.<name>_zigbee_ready` | `binary_sensor` (DIAGNOSTIC) | Zigbee-мост готов |
| `binary_sensor.<name>_matter_ready` | `binary_sensor` (DIAGNOSTIC) | Matter-контроллер готов |
| `binary_sensor.<name>_sub_pairing` | `binary_sensor` (DIAGNOSTIC) | Режим сопряжения |
| `sensor.<name>_subdevice_count` | `sensor` | Количество устройств, подключённых через хаб |

`sensor.<name>_subdevice_count` обновляется раз в час через `/devices/{id}/discovery`. Полезно для проверки что Zigbee-хаб не «потерял» дочерние устройства после рестарта.

---

### Колонки Sber (sber_speaker)

Категория охватывает: SberBoom Home, SberBoom Mini, SberPortal, SberBox, SberSatellite.

> **Архитектурное ограничение:** управление воспроизведением (play/pause/next) через Gateway REST API недоступно — Sber закрыл этот путь для сторонних клиентов. Экспонируется статус подключения и диагностика.

**Primary entity:** `binary_sensor.<name>` (device_class: `connectivity`)

**Дополнительные сущности:**

| Entity | Платформа | Описание |
|---|---|
| `binary_sensor.<name>_online` | `binary_sensor` (DIAGNOSTIC) | Подключена к сети |
| `binary_sensor.<name>_zigbee_ready` | `binary_sensor` (DIAGNOSTIC) | Zigbee-мост готов |
| `binary_sensor.<name>_matter_ready` | `binary_sensor` (DIAGNOSTIC) | Matter-контроллер готов |
| `binary_sensor.<name>_staros_has_hub` | `binary_sensor` (DIAGNOSTIC) | StarOS hub инициализирован |
| `binary_sensor.<name>_sub_pairing` | `binary_sensor` (DIAGNOSTIC) | Режим сопряжения |
| `binary_sensor.<name>_detector` | `binary_sensor` (DIAGNOSTIC) | Радар-детектор |
| `select.<name>_position` | `select` (DIAGNOSTIC) | Позиция в стерео-паре (none/left/right) |
| `light.sber_indicator_color` | `light` | LED-индикатор (общий для всех колонок, цвет HSV) |
| `sensor.<name>_subdevice_count` | `sensor` | Количество дочерних устройств хаба |

---

## Специальные сущности

### Sber-сценарии как кнопки HA

Каждый ваш сценарий из приложения «Салют!» создаётся как `button`-сущность под виртуальным устройством **«Sber Scenarios»**:

```
button.sberhome_scenarios_<slug_имени>
```

Например, сценарий «Уход из дома» → `button.sberhome_scenarios_ukhod_iz_doma`

Нажатие (в UI или через автоматизацию) → сценарий выполняется в Sber-облаке (POST `/scenario/v2/command`). Это тот же эффект, что и кнопка «Запустить» в приложении «Салют!».

**Пример:**

```yaml
automation:
  - alias: "Запустить сценарий «Уход из дома» при уходе"
    trigger:
      - platform: state
        entity_id: binary_sensor.sber_at_home
        to: "off"
    action:
      - service: button.press
        target:
          entity_id: button.sberhome_scenarios_ukhod_iz_doma
```

---

### Присутствие дома (at_home)

| Entity | Описание |
|---|---|
| `binary_sensor.sber_at_home` | Зеркалит глобальную переменную `at_home` из Sber-облака |
| `switch.sber_at_home` | Запись обратно в Sber: включить = «я дома», выключить = «меня нет» |

Используйте как `condition` или `trigger` в автоматизациях.

**Пример — синхронизация HA presence → Sber:**

```yaml
automation:
  - alias: "Установить at_home в Sber когда пришёл домой"
    trigger:
      - platform: state
        entity_id: device_tracker.my_phone
        to: "home"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.sber_at_home

  - alias: "Сбросить at_home в Sber при уходе"
    trigger:
      - platform: state
        entity_id: device_tracker.my_phone
        to: "not_home"
        for: "00:05:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.sber_at_home
```

---

### LED-индикатор колонок

`light.sber_indicator_color` — единая сущность, управляющая LED-кольцом на колонках Sber через `IndicatorAPI` (HSV цвет + яркость). Обновляется раз в час.

**Поддерживает:** `light.turn_on` (с `hs_color` и `brightness`), `light.turn_off`

**Пример — индикатор тревоги:**

```yaml
automation:
  - alias: "Красный индикатор при срабатывании датчика"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_dyma_kuhnya
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.sber_indicator_color
        data:
          hs_color: [0, 100]
          brightness: 255

  - alias: "Погасить индикатор когда тревога снята"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_dyma_kuhnya
        to: "off"
    action:
      - service: light.turn_off
        target:
          entity_id: light.sber_indicator_color
```

---

### Обновления прошивок (update)

`update.<device_name>_firmware` создаётся для каждого устройства, но **отключён по умолчанию** (слишком шумно при большом количестве устройств).

**Как включить:**

> Настройки → Устройства и службы → SberHome → выберите нужное устройство → «+N hidden entities» → включите «Firmware»

Когда Sber выпускает обновление — HA отображает золотой колокольчик в шапке. Фактическая установка прошивки выполняется через приложение «Салют!» (server-side rollout, установка из HA не реализована).

---

### Sber-группы как switch (v5.4.0+)

Каждая непустая группа устройств из приложения «Салют!» (тип `GROUP`) появляется в HA как `switch`:

```
switch.<group_name>
```

**Логика состояния:**

| Условие | Состояние HA |
|---|---|
| Хоть одно устройство группы включено | `on` |
| Все on_off-устройства группы выключены | `off` |
| В группе нет устройств с `on_off` (например, только шторы) | `unknown` |
| Все устройства группы offline | `unavailable` |

Включение/выключение отправляет единственную bulk-команду на Sber-сервер — он сам рассылает её по всем устройствам группы. Это быстрее и атомарнее, чем N отдельных команд из HA.

**Пример — управление группой:**

```yaml
automation:
  - alias: "Выключить освещение прихожей на ночь"
    trigger:
      - platform: time
        at: "23:30:00"
    action:
      - service: switch.turn_off
        target:
          entity_id: switch.sberhome_osveshchenie_prikhozheiy
```

---

### TTS-уведомления (notify, v5.6.0+)

Для каждого дома в аккаунте Sber регистрируется `notify`-сущность:

```
notify.sberhome_<slug_имени_дома>
```

Например, для дома «Мой дом» → `notify.sberhome_moy_dom`

Полное описание механизма и ограничений — в разделе [TTS surrogate — подробно](#tts-surrogate--подробно).

---

## HA events — sberhome_intent

Событие `sberhome_intent` отправляется в HA event bus каждый раз, когда в Sber-облаке срабатывает любой сценарий (голосовой, по расписанию, по датчику, по геолокации и т.д.).

### Payload события

| Поле | Тип | Описание |
|---|---|---|
| `name` | `str` | Имя Sber-сценария |
| `scenario_id` | `str` | UUID сценария |
| `event_time` | `str` | ISO-8601 UTC с микросекундами |
| `type` | `str` | `SUCCESS` / `ERROR` / `CANCELLED` |
| `trigger_type` | `str \| null` | Что запустило сценарий (см. ниже) |
| `home_id` | `str \| null` | UUID дома, где сработал сценарий |
| `account_id` | `str \| null` | Sber-аккаунт |
| `event_id` | `str \| null` | UUID события для дедупликации |
| `description` | `str \| null` | Описание сценария (включает HA-managed маркер для YAML-managed intents) |
| `slug` | `str \| null` | Slug listener'а (если событие огенерировано listener'ом), иначе `null` |
| `source` | `str` | `"sber_only"` (обычное срабатывание) / `"listener"` (огенерировано listener'ом) |

### Значения trigger_type

| Значение | Когда возникает |
|---|---|
| `PHRASES` | Голосовая команда через колонку Sber |
| `TIME` | Срабатывание по расписанию |
| `DEVICE` | Срабатывание по датчику (Sber-side automation) |
| `GEO_TIME` | Геофенс + время |
| `CONDITIONS` | Составное условие |
| `CHECK_DEVICE` | Проверка состояния устройства |
| `CHECK_SCENARIO` | Проверка сценария |
| `null` | Sber не указал тип (или ручной запуск) |

> **Ограничение Sber API:** поле с распознанным STT-текстом (что именно сказал пользователь) в event payload не передаётся. Доступен только сам факт срабатывания и тип триггера. Чтобы различать разные фразы одного сценария — создавайте отдельные сценарии (intents) под каждую фразу.

### Примеры автоматизаций с trigger sberhome_intent

**По имени сценария:**

```yaml
automation:
  - alias: "Реакция на голосовую команду «Доброе утро»"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          name: "Доброе утро"
    action:
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lampa_spalnya
        data:
          brightness_pct: 50
          color_temp_kelvin: 3000
      - service: climate.set_hvac_mode
        target:
          entity_id: climate.sberhome_konditsioner_spalnya
        data:
          hvac_mode: heat
```

**Только голосовые срабатывания:**

```yaml
automation:
  - alias: "Только голосовая команда — включить режим вечеринки"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          name: "Начать вечеринку"
          trigger_type: "PHRASES"
    action:
      - service: light.turn_on
        target:
          area_id: gostinaya
        data:
          effect: "Радуга"
```

**По slug listener'а (v5.5.0+):**

```yaml
automation:
  - alias: "Утренние сценарии по расписанию Sber"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          slug: morning_routine
    action:
      - service: cover.open_cover
        target:
          entity_id: cover.sberhome_shtory_spalnya
      - service: climate.set_temperature
        target:
          entity_id: climate.sberhome_konditsioner_spalnya
        data:
          temperature: 21
```

---

## YAML-конфигурация

### sberhome.intents (v5.2.0+)

YAML-intents позволяют декларативно описать голосовые сценарии прямо в `configuration.yaml`. При каждом reload они создаются или обновляются в Sber-облаке (additive — существующие пользовательские сценарии не удаляются).

**Базовая структура:**

```yaml
# configuration.yaml
sberhome:
  intents:
    - slug: morning                       # опционально, автогенерируется из name
      name: "Доброе утро"
      home: "Мой дом"                     # опционально, default: первый дом аккаунта
      phrases:
        - "доброе утро"
        - "проснуться"
      enabled: true                       # опционально, default: true
      description: "Утренний сценарий"   # опционально
      actions:
        - type: ha_event_only             # просто отправить HA-event sberhome_intent
```

**Указание дома (v5.3.0+):**

```yaml
# Приоритет: home_id > home > первый дом аккаунта
sberhome:
  intents:
    - slug: morning_home
      name: "Доброе утро дома"
      home: "Мой дом"               # резолв по имени (регистр и пробелы в конце игнорируются)
      phrases: ["доброе утро"]
      actions:
        - type: ha_event_only

    - slug: morning_dacha
      name: "Доброе утро на даче"
      home_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # явный UUID
      phrases: ["доброе утро на даче"]
      actions:
        - type: ha_event_only
```

**Поддерживаемые action-типы:**

```yaml
actions:
  # ha_event_only — только отправить HA-event sberhome_intent
  - type: ha_event_only

  # tts — произнести фразу через колонку Sber
  - type: tts
    phrase: "Доброе утро! Сегодня рабочий день."
    device_ids:
      - "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # UUID колонки из панели SberHome

  # device_command — отправить команду устройству
  - type: device_command
    device_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # UUID устройства
    attributes:
      - key: on_off
        type: BOOL
        bool_value: true
      - key: light_brightness
        type: INTEGER
        integer_value: 200
```

**Полный пример:**

```yaml
sberhome:
  intents:
    - slug: good_morning
      name: "Доброе утро"
      home: "Мой дом"
      phrases:
        - "доброе утро"
        - "просыпаться"
        - "начать день"
      actions:
        - type: ha_event_only
        - type: tts
          phrase: "Доброе утро! Запускаю утренний сценарий."
          device_ids: ["<uuid-колонки-в-спальне>"]
        - type: device_command
          device_id: "<uuid-лампы>"
          attributes:
            - key: on_off
              type: BOOL
              bool_value: true
            - key: light_brightness
              type: INTEGER
              integer_value: 100

    - slug: good_night
      name: "Спокойной ночи"
      home: "Мой дом"
      phrases:
        - "спокойной ночи"
        - "выключить всё"
      actions:
        - type: ha_event_only
```

**Автоматизация по YAML intent:**

```yaml
automation:
  - alias: "Утренний сценарий HA"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          name: "Доброе утро"
    action:
      - service: cover.open_cover
        target:
          entity_id: cover.sberhome_shtory_spalnya
      - service: climate.set_temperature
        target:
          entity_id: climate.sberhome_konditsioner_spalnya
        data:
          temperature: 22
          hvac_mode: heat
```

**Поведение при конфликтах:**

- YAML — единственный источник истины для сценариев с маркером `🤖 HA-managed (sberhome): slug=<slug>`.
- Если пользователь отредактирует такой сценарий в приложении «Салют!» — следующий reload YAML перезапишет его.
- Сценарии без YAML-counterpart (orphans) не удаляются автоматически — только предупреждение в логах.

**Применить изменения без перезапуска HA:**

```
Разработчик → Сервисы → sberhome.reload_intents
```

---

### sberhome.listeners (v5.5.0+)

Listeners — read-only подписка на Sber-события без создания сценариев в Sber. Позволяют ловить события от сценариев с любым триггером (расписание, датчик, геолокация), не только голосовые.

**Базовая структура:**

```yaml
# configuration.yaml
sberhome:
  listeners:
    - slug: morning_schedule               # уникальный идентификатор
      name: "Утреннее расписание"
      enabled: true                        # опционально, default: true
      description: "Ловим утренний сценарий Sber"   # опционально
      filter:                              # обязательно, минимум одно поле
        trigger_type: TIME
        scenario_name: "Доброе утро"      # опционально: точное имя сценария
```

**Поля фильтра:**

| Поле | Тип | Описание |
|---|---|---|
| `trigger_type` | `str` или `list[str]` | Тип триггера Sber-сценария. AND между полями, OR внутри списка |
| `scenario_name` | `str` | Точное имя сценария (нечувствительно к регистру и пробелам) |
| `scenario_id` | `str` | UUID сценария (exact match) |
| `home` | `str` | Имя дома (резолвится в UUID при старте HA) |
| `home_id` | `str` | UUID дома (exact match) |

Минимум одно поле обязательно.

**Допустимые значения trigger_type:**

`PHRASES`, `TIME`, `DEVICE`, `GEO_TIME`, `CONDITIONS`, `CHECK_DEVICE`, `CHECK_SCENARIO`, `UNDEFINED_TYPE`

**Полный пример с несколькими listeners:**

```yaml
sberhome:
  listeners:
    # Ловим утренний TIME-сценарий по расписанию
    - slug: morning_time
      name: "Утренние time-сценарии"
      filter:
        trigger_type: TIME
        scenario_name: "Доброе утро"

    # Ловим любой GEO или DEVICE сценарий в «Мой дом»
    - slug: geo_or_device_home
      name: "Гео или device дома"
      filter:
        trigger_type: [GEO_TIME, DEVICE]
        home: "Мой дом"

    # Ловим конкретный сценарий по UUID
    - slug: specific_scenario
      name: "Конкретный сценарий"
      filter:
        scenario_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

**Привязка автоматизации к listener:**

```yaml
automation:
  - alias: "Утреннее расписание Sber — реакция HA"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          slug: morning_time
    action:
      - service: cover.open_cover
        target:
          entity_id: cover.sberhome_shtory_gostinaya
      - service: switch.turn_on
        target:
          entity_id: switch.sberhome_rozetka_kofevar

  - alias: "Геофенс сработал — выключить свет"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          slug: geo_or_device_home
          trigger_type: "GEO_TIME"
    action:
      - service: light.turn_off
        target:
          area_id: all
```

**Ограничения listeners:**

- Listeners — **только чтение**. Они не создают и не изменяют сценарии в Sber.
- Sber-сценарий с нужным триггером должен быть заранее создан в приложении «Салют!».
- Изменение `listeners:` в YAML требует перезапуска HA (или вызова `sberhome.reload_intents` начиная с v5.5.1).
- Slug listener'а не может совпадать со slug intent'а — при коллизии listener отключается с предупреждением в лог.

---

## Сервисы HA

Все сервисы вызываются через **Разработчик → Сервисы** (Developer Tools → Services) или из автоматизаций.

### sberhome.refresh

Принудительное обновление состояний всех устройств через REST polling. Полезно после временной сетевой ошибки или перед чтением датчика в автоматизации, если нужна гарантированно свежая метрика.

```yaml
action:
  - service: sberhome.refresh
```

### sberhome.reload_intents

Перечитывает блок `sberhome.intents` и `sberhome.listeners` из `configuration.yaml` и синхронизирует с Sber. Не требует перезапуска HA.

Response payload содержит поля `intents_count` и `listeners_count`.

```yaml
action:
  - service: sberhome.reload_intents
```

### sberhome.send_raw_command

Отправляет произвольный `desired_state` в Sber API в обход стандартного маппинга. Debug-инструмент для экспериментов с wire-форматом.

```yaml
action:
  - service: sberhome.send_raw_command
    data:
      device_id: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      state:
        - key: "on_off"
          type: "BOOL"
          bool_value: true
        - key: "light_colour"
          type: "COLOR"
          color_value:
            hue: 120
            saturation: 100
            brightness: 50
```

### sberhome.send_custom_key / send_direction / play_channel

Специальные сервисы для управления телевизорами. Подробнее — в разделе [Телевизоры (tv)](#телевизоры-tv).

---

## Кастомная панель в сайдбаре

После установки интеграции в сайдбаре HA появляется кнопка **SberHome**. Панель построена на Lit (web components) и общается с backend через WebSocket API.

### Таб Devices

Основной рабочий инструмент. Показывает все устройства из Sber Gateway с возможностью:

- Включить/исключить устройство из HA (opt-in picker)
- Искать по имени
- Фильтровать по категории
- Переключать домá (dropdown «Все дома»)
- Открыть карточку устройства: сырые атрибуты, raw reported_state, assigned HA entity_id

Устройства неподдерживаемых категорий отображаются приглушённо с бейджем «не поддерживается» и не включаются в HA.

### Таб Automations

Содержит три сегмента:

**🎤 Intents** — управление голосовыми сценариями:

- Список всех Sber-сценариев с отображением `last_fired_at`
- Кнопка «+ Новый intent» — откроет schema-driven форму
- Кнопки редактирования и удаления для каждого intent
- Кнопка ▶ Test — программный запуск сценария (реальный `POST /run`, колонка озвучит TTS)
- Сценарии с неизвестными action-типами помечаются как «Sber-only» (read-only)

**⚡ Listeners** — список активных YAML-listeners (read-only):

- Slug, имя, summary фильтра, `last_fired_at`

**🔊 TTS** — управление TTS surrogate (v5.6.0+):

- Статус surrogate-сценариев per home (создан / не создан)
- Кнопка «Создать сейчас» (если surrogate не обнаружен)
- Тестовая форма: дом, фраза, выбор колонок, отображение latency
- Автогенерированный YAML-сниппет для копи-пасты в `configuration.yaml`

### Таб Monitor

DevTools для отладки:

| Инструмент | Описание |
|---|---|
| **State Diffs** | Дельта `reported_state` между тиками — показывает что именно изменилось, без полного payload |
| **Command Tracker** | Отслеживает отправленные команды и проверяет их применение в следующем `reported_state` (ловит silent rejection от Sber) |
| **Schema Validation** | Детектирует дрейф API на лету — помечает атрибуты с неожиданными типами |
| **Replay / Inject** | Подать синтетический WS-payload в coordinator для тестирования без физического устройства |
| **Per-device Diagnose** | Один клик → вердикт `ok` / `warning` / `broken` + конкретный следующий шаг |

### Таб Debug

- WS message log — кольцевой буфер входящих WS-сообщений с фильтрацией по топику и device_id
- Raw command interface (`sberhome.send_raw_command` через UI)
- Rooms management — просмотр и переименование комнат через `RoomAPI`

### Таб Settings

- Просмотр и изменение интервала polling
- Информация о токенах (срок действия без раскрытия значений)
- Trigger reauth

---

## Multi-home

Если к аккаунту Sber привязано несколько домов:

- Интеграция создаёт по одной `notify.sberhome_<slug>` на каждый дом.
- В панели SberHome — dropdown «Все дома» позволяет переключаться между домами в Devices и Automations tabs.
- Устройства из разных домов доступны одновременно и различаются по `device_info.configuration_url` или `device_info.location` (имя дома/комнаты).
- YAML intents/listeners: `home:` / `home_id:` указывает в какой дом отправлять сценарий. Без указания — первый дом аккаунта.
- `sberhome_intent` events содержат `home_id` — можно фильтровать в automation по конкретному дому.

**Пример автоматизации только для конкретного дома:**

```yaml
automation:
  - alias: "Реакция только на события из «Дача»"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          name: "Доброе утро"
    condition:
      - condition: template
        value_template: >
          {{ trigger.event.data.home_id == 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx' }}
    action:
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lampa_dacha_spalnya
```

---

## Световые эффекты (v5.4.0+)

Если прошивка лампы или LED-ленты поддерживает динамические сцены, HA автоматически добавляет `LightEntityFeature.EFFECT`. Список доступных эффектов отображается в стандартной light-card в Lovelace.

**Проверка поддержки:** эффекты появляются только если в `attributes[].light_mode.enum_values` устройства есть значение `"scene"`. Лампы без поддержки scene-режима feature не получают.

**Включить эффект:**

```yaml
action:
  - service: light.turn_on
    target:
      entity_id: light.sberhome_lenta_zal
    data:
      effect: "Радуга"
```

**Узнать доступные эффекты:** посмотреть атрибут `effect_list` в Developer Tools → States или в Lovelace light-card (dropdown).

**При неизвестном имени эффекта** — в лог пишется warning, лампа включается обычным `turn_on` без сцены.

**Примеры автоматизаций:**

```yaml
automation:
  - alias: "Световое шоу на праздник"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          name: "Начать вечеринку"
    action:
      - service: light.turn_on
        target:
          entity_id:
            - light.sberhome_lenta_gostinaya
            - light.sberhome_lenta_kuhnya
        data:
          effect: "Радуга"
          brightness_pct: 100

  - alias: "Романтическое освещение"
    trigger:
      - platform: event
        event_type: sberhome_intent
        event_data:
          name: "Романтический вечер"
    action:
      - service: light.turn_on
        target:
          entity_id: light.sberhome_lenta_spalnya
        data:
          effect: "Свеча"
          brightness_pct: 30
```

---

## TTS surrogate — подробно

> **🧪 EXPERIMENTAL.** Механизм работает за счёт runtime-редактирования Sber-сценария-болванки перед каждым вызовом. Каждый `notify.sberhome_*` = 2–3 API-вызова в Sber (PUT сценарий → POST /run, плюс GET при cache miss). Latency: ~500ms–2s. Sber может изменить wire-формат или начать ограничивать частые edits. **Не использовать для частых уведомлений (>1/мин).**

### Как это работает

1. При первом вызове `notify.sberhome_<home>` интеграция ищет в Sber-облаке сценарий с маркером в description (`ha-tts-surrogate-<home_id>`).
2. Если сценарий не найден — создаётся новый (1 дополнительный API-вызов). Surrogate-сценарий содержит guard-фразу «служебная фраза сурогата хатэтээс» — достаточно необычную, чтобы пользователь не произнёс её случайно.
3. PUT surrogate-сценарий с новым `pronounce_data.phrase` и `device_ids`.
4. POST `/scenario/v2/run` — Sber произносит фразу через указанные колонки.

### Базовый вызов

```yaml
automation:
  - alias: "Уведомление об ужине"
    trigger:
      - platform: time
        at: "19:00:00"
    action:
      - service: notify.send_message
        target:
          entity_id: notify.sberhome_moy_dom
        data:
          message: "Ужин готов"
```

### Выбор конкретных колонок

По умолчанию фраза произносится через **все колонки** указанного дома. Чтобы направить на конкретные устройства — передайте `device_ids` (raw Sber UUID, не HA entity_id):

```yaml
action:
  - service: notify.send_message
    target:
      entity_id: notify.sberhome_moy_dom
    data:
      message: "Только кухня слышит это сообщение"
      device_ids:
        - "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"   # UUID колонки из панели SberHome
```

UUID колонок можно найти:
- В панели SberHome → Devices → карточка устройства → поле «Device ID»
- В Developer Tools → States → `binary_sensor.<speaker_name>` → атрибуты

> `target` с HA `media_player` entity_id пока **не резолвится** — используйте `data.device_ids` для явного override. Поддержка будет добавлена в будущей версии.

### Управление через UI

Панель SberHome → **Automations** → сегмент **🔊 TTS**:

- Статус surrogate для каждого дома (создан / не создан)
- Кнопка «Создать сейчас» для домов без surrogate
- Тестовая форма с выбором дома, фразы и колонок — показывает реальный latency
- Автогенерированный YAML-сниппет

Для домов без колонок типа `sber_speaker` кнопка заменяется на бейдж «без колонок» — surrogate не может быть создан без хотя бы одной колонки в доме.

### Примеры автоматизаций

**Ежечасное время:**

```yaml
automation:
  - alias: "Объявлять время каждый час"
    trigger:
      - platform: time_pattern
        hours: "/1"
    action:
      - service: notify.send_message
        target:
          entity_id: notify.sberhome_moy_dom
        data:
          message: >
            Сейчас {{ now().strftime('%H:%M') }}
```

**Уведомление о датчике:**

```yaml
automation:
  - alias: "Озвучить тревогу о протечке"
    trigger:
      - platform: state
        entity_id: binary_sensor.sberhome_datchik_protechki_kuhnya
        to: "on"
    action:
      - service: notify.send_message
        target:
          entity_id: notify.sberhome_moy_dom
        data:
          message: "Внимание! Обнаружена протечка воды на кухне!"
      - service: cover.close_cover
        target:
          entity_id: cover.sberhome_klapan_voda
```

### Ограничения

| Ограничение | Описание |
|---|---|
| 1 surrogate на дом | Создаётся один сценарий-болванка, не зависит от количества вызовов |
| Конкурентные вызовы | При одновременных вызовах для одного дома — race condition на edit'е. Механизм защиты (per-home asyncio.Lock) добавлен в v5.7.0, но Sber может произнести «что-то» при очень близких вызовах |
| Cache invalidation | При ручном удалении surrogate-сценария в приложении «Салют!» — интеграция автоматически rediscover'ит или пересоздаёт его (v5.7.1) |
| Orphan-сценарии | После смены аккаунта или переустановки HA — surrogate-сценарии остаются в Sber. Удалять вручную через приложение «Салют!» |
| Rate limit | 2–3 API-вызова на каждый `notify`. Не для высокочастотных уведомлений (>1/мин) |
| Latency | ~500ms–2s на вызов |
