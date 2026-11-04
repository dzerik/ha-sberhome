# OpenSpec в ha-sberhome

Используем OpenSpec для изменений с несколькими сценариями поведения или
затрагивающих несколько подсистем. Начальный разбор открытых задач —
[backlog.md](backlog.md). Проверенные сведения о коде и ограничения реализации
находятся в `design.md` соответствующего изменения.

## Работа с изменением

CLI закреплён на версии 1.16.0 в `scripts/openspec.sh`; нужен Node.js 22.12+
и npm. Первый запуск скачивает инструмент. Зависимости Python не меняются.
Команды выполняются из корня репозитория:

```bash
./scripts/openspec.sh list
./scripts/openspec.sh status --change add-csafront-email-otp
./scripts/openspec.sh instructions apply --change add-csafront-email-otp --json
./scripts/openspec.sh validate --all --strict
```

Перед работой над issue прочитай его обсуждение, затем `proposal.md`, delta-spec,
`design.md` и `tasks.md`. Отмечай задачи после проверки результата. Если новых
данных недостаточно для реализации, уточни решение в `design.md` и сохрани
незавершённые задачи открытыми.

Опубликованные изменения и незавершённые проверки:

- №67 и №68 — порядок действий, REGIME и CONDITIONS выпущены в
  [v6.4.0b5](https://github.com/dzerik/ha-sberhome/releases/tag/v6.4.0b5).
  Требования и результаты находятся в `specs/` и `changes/archive/`.
- №62 — обновление домашних переменных и кнопки Stop/Cancel;
  [v6.4.0b6](https://github.com/dzerik/ha-sberhome/releases/tag/v6.4.0b6), [PR #85](https://github.com/dzerik/ha-sberhome/pull/85).
  [Отчёт](changes/archive/2026-11-04-sync-home-mode-and-scenario-controls/validation.md)
  сохранён в архиве. Живые проверки Stop и Cancel завершены; доставка внешнего push при настоящем
  переключении дома остаётся для подтверждения при обычном использовании.
- `add-csafront-email-otp` — №80: email-подтверждение реализовано и выпущено
  в v6.4.0b5 по публичному официальному клиенту провайдера;
  [проверки](changes/add-csafront-email-otp/validation.md).
  Остаётся живой вход аккаунтом с email-фактором, поэтому change не архивирован.

Текущее исследование №61/№62 —
[`preserve-scenario-schedules`](changes/preserve-scenario-schedules/proposal.md):
сохранность TIME и проверка изменения/удаления расписаний. Реализация пока
не начата; [результаты](changes/preserve-scenario-schedules/validation.md).

`changes/*/specs/` описывают предлагаемое поведение. Пока изменения не
реализованы и не архивированы, эти требования остаются предложением.
После реализации и проверки команда `archive <change>` переносит требования
в `specs/` и сохраняет историю изменения. Основные спецификации описывают
реализованное поведение кода; публикация релиза выполняется отдельно.
Архивация не закрывает GitHub issue.

## Интеграция с агентами

Инициализация выполнена с `--tools none`: в этой рабочей среде каталоги
`.agents/` и `.codex/` доступны только для чтения. CLI и все артефакты работают
без slash-команд. Для настройки команд в обычном checkout с доступным для
записи каталогом агента можно выполнить:

```bash
./scripts/openspec.sh init --tools codex
```

Правила разработки остаются в `AGENTS.md`, сведения для пользователей — в
`README.md` и `USAGE.md`; спецификации описывают проверяемые контракты поведения.
