# Changelog

## [1.0.0] — 2026-04-15

Первый релиз **SberHome** как самостоятельной интеграции.

Проект начался как форк [altfoxie/ha-sberdevices](https://github.com/altfoxie/ha-sberdevices) и к версии 2.10.x был полностью переписан — ни одной строки оригинального кода не осталось. Этот релиз отделяет новую кодовую базу под собственным именем и HA-доменом (`sberhome`).

### Состояние на старте

- **Платформы HA:** light, switch, sensor, binary_sensor, climate, cover, fan, humidifier, media_player, number, select, event (12)
- **Категории устройств:** 28 из официальной спецификации Sber Smart Home
- **Авторизация:** OAuth2/PKCE через `id.sber.ru`, companion token → `gateway.iot.sberdevices.ru/gateway/v1/*`
- **Архитектура:** `DataUpdateCoordinator` + optimistic updates, declarative registry of entities
- **SSL:** Russian Trusted Root CA, lazy init через executor
- **Тесты:** 144 теста, покрытие ~86%
- **Переводы:** en, ru, be, kk

### История до 1.0.0

Коммиты v0.x–v2.10.2 находятся в архивном репозитории [dzerik/ha-sberdevices](https://github.com/dzerik/ha-sberdevices) (fork от @altfoxie). Новая история чистая — с 1.0.0.
