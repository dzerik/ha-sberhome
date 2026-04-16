# SberHome for Home Assistant

Интеграция умного дома Сбер (приложение «Салют!») в Home Assistant.

Поддерживает 28 категорий устройств: освещение, розетки/реле, датчики, шторы, климат, пылесосы, медиаплееры и др. — через Sber Gateway API (`gateway.iot.sberdevices.ru`) с OAuth2/PKCE авторизацией через `id.sber.ru`.

## Поддерживаемые устройства

Реализованы все **28 категорий** из официальной спецификации Sber Smart Home:

### Освещение
- Умные лампы (`light`) — on/off, яркость, цвет, температура
- Светодиодные ленты (`led_strip`) — + sleep_timer

### Электрика
- Умные розетки (`socket`) — switch + напряжение/ток/мощность + child_lock
- Реле (`relay`) — switch + напряжение/ток/мощность

### Датчики
- Температуры/влажности (`sensor_temp`) — температура, влажность, давление + sensitivity, temp_unit
- Протечки воды (`sensor_water_leak`)
- Открытия двери/окна (`sensor_door`) — + tamper_alarm, sensitivity
- Движения (`sensor_pir`) — + sensitivity
- Дыма (`sensor_smoke`) — + alarm_mute
- Утечки газа (`sensor_gas`) — + alarm_mute, sensitivity
- Все датчики: battery, signal_strength, battery_low

### Шторы / ворота
- Шторы (`curtain`), жалюзи (`window_blind`), ворота (`gate`), клапаны (`valve`) — open/close/position + open_rate

### HVAC (климат) — полное покрытие всех фич spec
- Кондиционеры (`hvac_ac`) — current+target temp, humidity, fan speed (5), hvac_mode (cool/heat/dry/fan/auto), air_flow_direction, target humidity, night_mode, ionization
- Обогреватели (`hvac_heater`) — current+target temp, fan speed, thermostat_mode (eco/comfort/boost)
- Радиаторы (`hvac_radiator`) — current+target temp 25–40°C step 5
- Бойлеры (`hvac_boiler`) — current+target temp 25–80°C step 5, thermostat_mode, heating_rate
- Тёплый пол (`hvac_underfloor_heating`) — 25–50°C step 5, thermostat_mode, heating_rate
- Вентиляторы (`hvac_fan`) — speeds + direction
- Очистители воздуха (`hvac_air_purifier`) — speeds, night_mode, ionization, aromatization, decontaminate, replace_filter/ionizator diagnostics
- Увлажнители (`hvac_humidifier`) — current humidity + target, mode (5 speeds), night_mode, ionization, water_level, water_low diagnostics

### Бытовая техника
- Чайники (`kettle`) — switch + target_temp + water_level + water_temp + child_lock
- Роботы-пылесосы (`vacuum_cleaner`) — start/pause/return/locate + battery + program
- Телевизоры (`tv`) — source/volume/channel/mute

### Другое
- Сценарные выключатели (`scenario_button`) — события click/double_click
- Домофоны (`intercom`) — online
- Хабы (`hub`) — online

## Что изменено по сравнению с оригиналом

- **DataUpdateCoordinator** — единый опрос API вместо отдельного запроса на каждое устройство
- **Исправлен SSL** — убран `tempfile`, используется `ssl.create_default_context(cadata=...)`, нет блокировки event loop
- **Исправлен `supported_color_modes`** — устранена ошибка `Invalid supported_color_modes` (HA 2025.3+)
- **Исправлен config flow** — entry больше не создаётся при ошибке авторизации
- **Обработка ошибок** — `ConfigEntryNotReady` при недоступности API, `ConfigEntryAuthFailed` при проблемах с токеном
- **Исправлен `set_device_state`** — теперь использует метод `request()` с retry и обновлением токена
- **Корректный UTC timestamp** — `datetime.now(timezone.utc)` вместо `datetime.now() + "Z"`
- **Закрытие HTTP-клиентов** при выгрузке интеграции
- **Улучшенная авторизация** — удобная HTML-страница с инструкциями вместо консоли разработчика
- **Датчики** — поддержка Zigbee-сенсоров (температура, влажность, протечка, дверь, движение)
- **Reauth Flow** — автоматическое предложение повторной авторизации при истечении токена
- **Options Flow** — настраиваемый интервал опроса API (10–300 секунд)
- **Diagnostics** — поддержка диагностики для отладки (с автоматической редакцией токенов)
- **Локализация** — русский, английский, казахский, белорусский, узбекский
- **739 тестов** — API, coordinator, config flow, auth, entity, diagnostics + все 13 платформ + 285 тестов нового `aiosber/` ядра
- **Декларативная архитектура** — `registry.py` с dataclass-дескрипторами; новое устройство добавляется одной строкой
- **Полное покрытие sber spec** — все 28 категорий и все features реализованы (HVAC: current temp, thermostat_mode, heating_rate, ionization, aromatization, decontaminate; scenario_button до 10 кнопок + directional; replace_filter / water_low / tamper / alarm_mute)
- **Standalone-ядро `aiosber/`** — async-клиент Sber Gateway API без HA-зависимостей (см. ниже)
- **Intercom buttons** (`button.intercom_unlock`, `button.intercom_reject_call`) — управление домофоном из HA
- **Двустворчатые шторы / ворота** — отдельные cover-сущности `<device>_left` и `<device>_right`
- **TV IR-style commands** — entity services `sberhome.send_custom_key`, `sberhome.send_direction`, `sberhome.play_channel`

## Архитектура

Проект разделён на два слоя:

### `custom_components/sberhome/aiosber/` — standalone async-ядро

Чистый async Python-клиент Sber Gateway API без зависимостей от Home Assistant.
Готов к выделению в отдельный PyPI-пакет (см. CLAUDE.md → 2.0.0).

```python
from custom_components.sberhome.aiosber import (
    SberClient, AttributeValueDto, AttrKey, ColorValue,
)

async with await SberClient.from_companion_token("...") as client:
    devices = await client.devices.list()
    await client.devices.set_state(devices[0].id, [
        AttributeValueDto.of_color(
            AttrKey.LIGHT_COLOUR,
            ColorValue(hue=120, saturation=100, brightness=80),
        ),
    ])
```

Слои:
- **`auth/`** — OAuth2 PKCE через `id.sber.ru` + companion token + auto-refresh.
- **`transport/`** — HTTP (httpx + retry + headers) + WebSocket (reconnect + dispatch) + lazy SSL.
- **`api/`** — `DeviceAPI`, `GroupAPI`, `ScenarioAPI`, `PairingAPI` (Matter), `IndicatorAPI`.
- **`dto/`** — 30+ dataclass'ов + 47 wire-enum'ов (полная спецификация протокола).

CLI-примеры в `examples/list_devices.py`, `set_color.py`, `ws_listen.py`.

### `custom_components/sberhome/` — HA-адаптер

Тонкий слой поверх `aiosber/`. Платформы: light, switch, sensor, binary_sensor,
climate, cover, fan, humidifier, media_player, number, select, event, button (13).

## Установка

### Через HACS (рекомендуется)

1. Установить [HACS](https://hacs.xyz/)
2. **HACS** → **Integrations** → **3 точки** → **Custom repositories**
3. Заполнить форму:
    * **Repository**: `https://github.com/dzerik/ha-sberhome`
    * **Category**: `Integration`
4. Перезапустить Home Assistant

### Вручную

Скопировать директорию `custom_components/sberhome` в папку `custom_components/` вашей конфигурации Home Assistant.

## Настройка

1. **Настройки** → **Devices & services** → **Add integration**
2. Найти **SberHome**
3. Откроется страница авторизации с инструкциями
4. Нажмите **«Войти через Сбер ID»** — в новой вкладке откроется страница входа
5. Авторизуйтесь через Сбер ID
6. После входа браузер покажет ошибку — это нормально. Скопируйте **URL из адресной строки** (он начинается с `companionapp://`)
7. Вернитесь на страницу авторизации, вставьте URL в поле и нажмите **«Подтвердить»**

## Лицензия

MIT — см. [LICENSE](LICENSE)  