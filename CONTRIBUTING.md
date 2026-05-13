# Contributing to ha-sberhome

Спасибо что хотите внести вклад! Этот документ описывает базовый
процесс — установку dev-окружения, тесты, стиль, и порядок отправки
изменений.

## Перед тем как открывать issue

1. Проверь [существующие issues](https://github.com/dzerik/ha-sberhome/issues)
   — твой случай возможно уже обсуждается.
2. Проверь [CHANGELOG.md](CHANGELOG.md) — баг мог быть исправлен в
   свежей версии (`HACS → SberHome → Update`).
3. Прочитай [USAGE.md](USAGE.md) — справочник по сущностям и
   ожидаемому поведению.

## Issue templates

GitHub предложит шаблон при создании issue:

- **🐛 Bug report** — для ошибок: что происходит, что ожидалось,
  версия интеграции, версия HA, логи.
- **💡 Feature request** — для новой функциональности или категории
  устройств.

## Dev environment

```bash
git clone https://github.com/dzerik/ha-sberhome.git
cd ha-sberhome
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
pip install -e .
```

## Тесты

```bash
# Все тесты с coverage
pytest

# Один файл / один тест
pytest tests/test_light.py
pytest tests/test_light.py::test_turn_on

# Без coverage (быстрее)
pytest --no-cov tests/test_api.py
```

Текущий показатель: **1307 passed / 13 skipped** (v5.7.1). Регрессии
в существующих тестах — блокер для merge.

## Линт

```bash
ruff check custom_components/sberhome tests
ruff format --check custom_components/sberhome tests
```

Конфигурация — `pyproject.toml`:
- target Python: 3.12+
- line length: 100
- rules: E, F, W, I, UP, B, SIM

Если `format` показывает diff — запусти `ruff format custom_components/sberhome tests` чтобы применить.

## Архитектура

Перед нетривиальной правкой прочитай [`CLAUDE.md`](CLAUDE.md) —
там описана архитектурная парадигма (hexagonal split на standalone
`aiosber/` core и тонкий HA-адаптер). Ключевые правила:

1. **`aiosber/` НЕ импортирует ничего из HA** — `homeassistant.*`,
   `voluptuous`, `aiohttp` запрещены. CI это проверяет.
2. **`aiosber/` без глобального state** — всё через инстансы и DI.
3. **DTO — pure dataclasses без бизнес-логики.**
4. **HA-адаптер тонкий** — только склейка + перевод исключений
   + интеграция в HA-lifecycle.

## Добавление нового устройства

1. Найди `image_set_type` Sber'а в логах или через панель «Debug».
2. Маппинг `image_set_type → category` в `sbermap/spec/ha_mapping.py:IMAGE_TYPE_TO_CATEGORY`.
3. Если категории ещё нет — добавь спецификацию features
   в `sbermap/transform/category_specs.py` и `feature_specs.py`.
4. Платформенные модули (`sensor.py`, `binary_sensor.py`, `switch.py`,
   `number.py`, `select.py`) — generic, читают реестр. Нетривиальные
   платформы (`light`, `climate`, `cover`, `fan`, `humidifier`,
   `media_player`, `vacuum`) имеют свои per-category ветки.
5. Добавь хотя бы один тест на новую категорию.

## Pull Request

1. Создай feature-ветку: `git checkout -b feat/my-feature`
2. Закоммить с понятным message (см. ниже).
3. Убедись что тесты + lint зелёные.
4. Подними версию в `pyproject.toml` и `manifest.json` (см. SemVer
   правила в `CLAUDE.md`).
5. Добавь запись в `CHANGELOG.md`.
6. Открой PR. Шаблон заполнится автоматически — следуй ему.

## Commit messages

Conventional Commits style:

```
тип: краткое описание (RU/EN на выбор)

Подробное описание изменений если нужно.
```

Типы:
- `feat` — новая функциональность
- `fix` — исправление бага
- `refactor` — рефакторинг без изменения функциональности
- `docs` — обновление документации
- `chore` — технические изменения (deps, config, релиз)
- `perf` — улучшение производительности
- `test` — добавление/обновление тестов

## Семантическое версионирование

См. `CLAUDE.md` секция «Semantic Versioning».

- **PATCH** (5.7.1 → 5.7.2): bugfix, рефакторинг, обновление зависимостей.
- **MINOR** (5.7.x → 5.8.0): новая функциональность, новая категория
  устройств, новые YAML-настройки. Backwards-compatible.
- **MAJOR** (5.x → 6.0.0): breaking changes (удаление deprecated,
  изменение формата).

## Лицензия

Контрибьюты лицензируются под MIT — той же, что и проект.
См. [LICENSE](LICENSE).
