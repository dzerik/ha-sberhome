# Проверки исправления питания Salute TV — №95

## Воспроизведение

На базе raw JSON из [№95](https://github.com/dzerik/ha-sberhome/issues/95)
воспроизведено ложное off: reported on_off=false с epoch-меткой,
desired=true без last_sync. Sanitised regression сохраняет существенные
значения, но не реальные device/group IDs, серийные номера и сведения аккаунта.
Не следует смешивать этот случай с docs/tv.json другого TV, у которого
reported=false имеет реальное время.

Первый запуск новых регрессий: 9 ожидаемых падений, 6 passed.
После исправления проверены unknown/assumed, явные on/off через сервисы HA,
literal PUT payload true/false, cloud rejection, offline и возвращение
подтверждённого состояния. Совпадающий desired сохраняет достоверность report.

Ревью выявило сравнение Python 0==False/1==True: невалидный числовой report
ошибочно подтверждал desired. Два дополнительных HA-теста сначала падали,
затем прошли после проверки bool-типа. Плохой строковый BOOL также unknown.

## Результаты

- 20 HA/FakeCloud регрессий в tests/test_tv_power.py.
- Focused TV/mapper suite: 84 passed.
- Повторное независимое read-only ревью: 62 focused tests passed, замечаний нет.
- Финальный полный pytest: **3086 passed**, 5 предупреждений,
  покрытие **99.21%**. База до изменений: 3066 passed, 5 предупреждений, 99.17%.
- Ruff check/format и mypy (173 source files): passed.
- Первый CI использовал Ruff 0.17.6 и выявил SIM102 в прежнем light.py;
  локальный Ruff был 0.15.13. Условие объединено без изменения ветвления,
  Ruff 0.17.6 check/format проходят. Light/TV suite: 43 passed.
  Дополнительный коммит поднял версию b9→b10; b9 не публиковалась.
- Strict OpenSpec: passed до архивации; после переноса требований проверяется повторно.

## Frontend и пределы проверки

Для HA 2026.11.3 проверен закреплённый frontend 20261028.8:
[manifest](https://github.com/home-assistant/core/blob/2026.11.3/homeassistant/components/frontend/manifest.json),
[computeMediaControls](https://github.com/home-assistant/frontend/blob/20261028.8/src/data/media-player.ts).
assumed_state=true при поддержке TURN_ON/TURN_OFF включает две явные команды.
Это контракт официального frontend; визуальная проверка на Salute TV не
выполнялась. Собственные переводы и дополнительные entity IDs не нужны.

На настоящие устройства power-команды не отправлялись. Доставка команды и
физическое выключение требуют проверки автора issue после обновления.
Поэтому публикация исправления сама по себе не закрывает №95.

Версия 6.4.0b10 поднята штатным bump script. PR/CI и подписанный prerelease
публикуются после локальных проверок; фактические результаты фиксируются в №95.
