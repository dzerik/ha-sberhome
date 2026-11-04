# Проверка исправления переводов редактора

Дата: 2026-11-04. Версия: 6.4.0b4.

## Воспроизведение и причина

Исходный симптом зафиксирован пользователем в docs/img_3.png и docs/img_4.png:
в summary и форме видны intents.regime_* и intents.period_* вместо подписей.
Read-only HTTP GET подтвердил, что modal, i18n/index.js и dicts.js на HA
совпадают с локальными SHA-256; словарь содержит новые ключи.

Регрессия `test_upgraded_intent_modal_refreshes_previously_loaded_translations`
сначала вычисляет старый i18n без ключей regime/period, обновляет файлы и
загружает настоящий modal с новым ?v. До исправления тест падал:
`AssertionError: ru: stale translation regime_title` (воспроизведено дважды).
После передачи v через modal → index → dicts проверка проходит во всех пяти
локалях, включая summary трёх команд. Причина воспроизведённого сбоя —
неверсионированные зависимости при версионированном родительском компоненте.

## Браузер

Настоящий Lit-компонент в headless Chrome. Сервер фикстуры отдаёт старый
unversioned dicts.js с Cache-Control: public, max-age=86400. В том же документе
сначала загружается старый i18n, затем новый modal. Подтверждены отдельные
запросы index.js?v=6.4.0b4 и dicts.js?v=6.4.0b4, корректные подписи в DOM на
ru/en/be/kk/uz и отсутствие ошибок JS. hass.callWS и устройства — тестовые.

Скриншоты просмотрены визуально:

- [Desktop, 1280 × 1050](desktop.png)
- [Mobile, 390 × 844](mobile.png)

## Автоматические проверки

- Full pytest: **2936 passed**, 5 warnings, 49.86 s, coverage **99.17%**.
- Frontend suite: **150 passed**.
- Ruff check и format --check: успешно, 353 файла.
- Mypy: ошибок нет, 171 исходный файл.
- OpenSpec strict validate и git diff --check: успешно.

## Деплой

SSH/tar.gz, до замены подтверждено соответствие всех 217 файлов ранее
установленной 6.4.0b3. Проверка конфигурации прошла, перезапуск инициирован.
Резервная копия:
`/config/.sberhome-deploy/20261104T111159Z/sberhome-before.tar.gz`.

Проверка после перезапуска прошла: runtime 6.4.0b4, polling успешен,
consecutive_failures=0. Все 217 SHA-256 совпадают с локальными файлами.
HTTP GET modal, i18n/index.js и dicts.js с ?v=6.4.0b4 возвращают точные
локальные версии файлов.
Облачные сценарии при этой проверке не создаются, не меняются и не запускаются.
