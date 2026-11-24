# Design

## Evidence

В raw JSON №95 у модели dt_salute_tv_l объявлена commands.on_off.
reported=false имеет last_sync=1970-01-01T00:00:00Z; desired=true — null.
На исходном коде DTO→mapper воспроизведён media_player=off.
Это отличается от пользовательского docs/tv.json другого TV, где false
имеет реальную метку времени. Полные дампы с идентификаторами в regression
не копируются: тест использует минимальную обезличенную форму.

Официальный [контракт TV](https://developers.sber.ru/docs/ru/smarthome/c2c/tv)
объявляет online и on_off обязательными, но не подтверждает корректную
обратную связь конкретного устройства.

HA 2026.11.3 закрепляет frontend 20261028.8 в
[manifest](https://github.com/home-assistant/core/blob/2026.11.3/homeassistant/components/frontend/manifest.json).
Его [computeMediaControls](https://github.com/home-assistant/frontend/blob/20261028.8/src/data/media-player.ts)
возвращает отдельные turn_on/turn_off при assumed_state=true.
Один unknown без assumed_state недостаточен. Строки/иконки принадлежат HA.

## Approach

Mapper не использует TV on_off с явной epoch-меткой 1970/0001.
MEDIA_PLAYER builder сохраняет None вместо bool-default off и отдаёт
assumed_state для неизвестного питания. Если свежий desired меняет
reported, mapper также отмечает его assumed. Совпадающий desired не
обесценивает подтверждённое состояние. Пустой timestamp у явно переданного
reported BOOL сохраняет legacy-поведение; epoch в отличие от отсутствия
явно означает неинициализированный снимок.

Adapter публикует state и assumed_state. TURN_ON/TURN_OFF уже отправляют
BOOL true/false независимо от текущего state. Connectivity остаётся
ответственностью available; online не интерпретируется как питание.
Raw cache и правила desired остальных платформ не меняются.

## Validation boundary

HA/FakeCloud проверяет публичный state/attributes и реальный запрос PUT через
сервисы HA. Проверяются epoch, missing, legacy BOOL, подтверждение,
pending desired, cloud rejection и offline. Фактическая доставка и действие
команды на Salute TV требуют подтверждения автора после обновления.
