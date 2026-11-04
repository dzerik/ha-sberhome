# Проверки lifecycle automation entities — №62

## Объём

Исправляются обнаружение, имена, availability и сохранность registry существующих
home/scenario/group entities. Исходные дефекты воспроизведены в
[исследовании](../../../research/2026-11-04-issue-62-entity-lifecycle.md).
Новые cloud endpoints, изменение bulk-команд и optimistic desired/reporting
в этот объём не входят.

## Red → green

Проверки выполнялись на настоящем тестовом Home Assistant 2026.10.4 с FakeCloud
и MockTransport; сеть Сбера заменена тестовым транспортом.

- До исправления regression неизменённой GROUP терял запись entity registry
  после maintenance; после защиты identifier `groups` проходит вместе с
  существующими registry maintenance тестами (10 passed).
- Следующий набор дал 11 ожидаемых падений на discovery, переименовании,
  списке домов, orphan membership и push невыбранного участника.
- После исправлений пять затронутых подсистем: 70 passed.
- Первоначальный `tests/test_automation_lifecycle.py`: 20 passed, включая пять локалей,
  disabled_by, custom name/icon, возврат ID, unload и reload.
- Независимое ревью выявило два края: успешное удаление дома при ошибке
  запроса сценариев и восстановление группы по push невыбранного участника
  после сбоя polling. Оба сначала воспроизведены падающими регрессиями.
  Проверка push также контролирует неизменность таймера и выбранных device data.
- Финальный lifecycle-набор: **22 passed**. После исправлений ревью
  lifecycle/scenario/push polling вместе: **54 passed**.

Проверяется фактический HA state и entity/device registry, а не только
создание объектов классов. При исчезновении cloud объекта сущности остаются
в registry, становятся unavailable и восстанавливаются с прежними ID.
Существующие тесты switch/button/group проверяют адресные команды; тесты
push polling проверяют сохранение расписания полного опроса.

## Полные проверки

- `PYTHONPATH=. .venv/bin/pytest`: **3066 passed**, 5 предупреждений,
  покрытие **99.17%**. До изменений: 3044 passed, 5 предупреждений, 99.15%.
- `ruff check custom_components/sberhome tests`: passed.
- `ruff format --check custom_components/sberhome tests`: passed.
- `mypy custom_components/sberhome`: 173 source files, passed.
- `openspec validate --all --strict`: passed до и после архивации.
- Независимое read-only ревью: оба P2 исправлены и повторно проверены;
  открытых замечаний нет, код готов к merge. Два внешних regression probe
  ревьюера также проходят. Отложены discovery домашнего binary_sensor
  и переработка optimistic semantics как отдельные задачи.

## Границы проверки и публикация

Реальные устройства и домашний режим не переключались. Эти регрессии
доказывают lifecycle на HA/FakeCloud, но не доставку внешнего push от Сбера
и не фактическое исполнение bulk-команды настоящей группой.
Динамическое обнаружение и имена домов в этом изменении относятся к writable
switch; прежний binary_sensor домашнего режима не расширяется новым discovery.

Версия 6.4.0b8 подготовлена штатным `scripts/bump_version.py beta`.
PR, CI и подписанный prerelease публикуются после локальных проверок;
фактические ссылки и результаты публикации будут записаны в issue №62.
Архив OpenSpec фиксирует реализованное поведение и не закрывает issue.
