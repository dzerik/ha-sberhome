# Проверки ручного сброса авторизации

Версия 6.4.0b12. Требование владельца проекта: полный локальный сброс
авторизации обоих способов и обоих API-каналов без удаления интеграции.

- Исходная проверка auth/config flow: 88 passed.
- RED: отсутствует меню; старые stores сохраняют/читают credentials после смены
  поколения; пустой Сбер ID при restart обращается к облаку; старый flow
  способен завершить вход после reset.
- Независимый review выявил stale reauth во время async_create_flow,
  позднее создание HTTP/PKCE/SMS и оставшийся открытым gateway probe,
  потерю идентичности legacy entry без unique_id. Воспроизведены через Events
  и настоящий HA FlowManager; исправлены с RED→GREEN regression tests.
- Итоговые focused auth/reset/options: **122 passed**.
- Полный pytest: **3109 passed, 5 прежних предупреждений, coverage 99.23%**.
- Ruff check/format: passed (362 files); mypy: passed (173 source files).
- Strict OpenSpec перед архивированием: 9 passed, 0 failed.

Проверены остановка HTTP/WS/polling, сохранение непустых device/entity registry
и options, отмена, unload failure, оба способа входа, обновление прежней записи,
stale store read/save/clear, pending flow abort и клиенты, рестарт до reauth,
проверка поколений и сохранение identity для старых записей. Неизвестный legacy
аккаунт не очищается. Все UI-строки есть в en/ru/be/kk/uz и strings.json.

Живой reset не выполнялся: он требует интерактивного входа владельца и
временно отключает интеграцию. Публикация и установка кода отслеживаются
отдельно в GitHub/release workflow. Серверный отзыв сессий, browser cookies и
исторические HA backups не входят в локальный reset.
