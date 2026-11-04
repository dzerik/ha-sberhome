# Открытые issues: стартовый разбор

Исходный снимок на 2026-11-04, базовый код `5e966fc` (6.2.2).
№67 и №68 опубликованы в [v6.4.0b5](https://github.com/dzerik/ha-sberhome/releases/tag/v6.4.0b5)
через [PR #84](https://github.com/dzerik/ha-sberhome/pull/84); соответствующие issues закрыты.
В №80 опубликован ответ с бетой, issue остаётся открытым до живого email-входа.
Проверены все 9 открытых issues и их комментарии через GitHub; PR обновления
зависимостей в этот список не входят. Статусы ниже — локальная оценка готовности,
а не изменения статусов GitHub. Приоритет предложен для пилота OpenSpec.

| Issue | Что подтверждено в коде | Следующий шаг |
| --- | --- | --- |
| [#80: email-код после SMS](https://github.com/dzerik/ha-sberhome/issues/80) | Реализовано в 6.3.1b1: отдельный email-шаг, initialize/verify по официальному клиенту, переводы и регрессии | [Проверки](changes/add-csafront-email-otp/validation.md). Нужен живой вход аккаунтом с email-фактором; до него change не архивируется |
| [#78: нет companionapp URL](https://github.com/dzerik/ha-sberhome/issues/78) | Страница авторизации ожидает ручную вставку `companionapp://`; причина зависания у провайдера не установлена | Воспроизвести с данными о браузере и очищенной цепочкой редиректов; после диагностики определить изменение |
| [#67: порядок действий](https://github.com/dzerik/ha-sberhome/issues/67) | Добавлены ↑/↓, исправлены порядок при decode→encode и задержки дубликатов | Опубликовано в v6.4.0b5 (PR #84); [проверки и скриншоты](changes/archive/2026-11-04-reorder-scenario-actions/validation.md), основной контракт в `specs/scenario-action-order/` |
| [#68: редактирование unknown](https://github.com/dzerik/ha-sberhome/issues/68) | В 6.4.0b5 реализованы REGIME_COMMAND и редактор CONDITIONS: И с событием и проверками, ИЛИ с альтернативами, сенсорные атрибуты, raw/metadata и пять локалей. Живой CRUD проверен, тестовые сценарии удалены | [Проверки групп](changes/archive/2026-11-04-edit-nested-scenario-conditions/validation.md). Статус CHECK_SCENARIO сохраняется точным кодом без неподтверждённого enum; неизвестные формы остаются read-only. Выпущено в v6.4.0b5, issue закрыт PR #84 |
| [#64: Aura-хаб](https://github.com/dzerik/ha-sberhome/issues/64) | `DeviceDto.children` уже есть; `sub_pairing` уже объявлен в `feature_specs.py` для колонок/хабов. Есть тесты радара Aura, но поиск не выявил фикстуру полного дерева настроек Aura | Проверить фактический маппинг pairing, оставшийся счётчик children и получить очищенный дамп для проверки заявленных 8 сущностей |
| [#63: Aura EQ](https://github.com/dzerik/ha-sberhome/issues/63) | Сам issue требует подтверждения EQ в приложении и совместимости формата | Отложено до подтверждения на Aura; добавление product prefix без этих данных преждевременно |
| [#62: automation entities](https://github.com/dzerik/ha-sberhome/issues/62) | В 6.4.0b6 добавлены WS-перечитка домашних переменных и stop/cancel-кнопки; динамическое обнаружение и прежние unique_id проверены. Stop прерывает выполнение; cancel отменяет ожидающий запуск и даёт понятную ошибку 409 для running | [Проверки](changes/archive/2026-11-04-sync-home-mode-and-scenario-controls/validation.md). Выпущено в [v6.4.0b6](https://github.com/dzerik/ha-sberhome/releases/tag/v6.4.0b6), [PR #85](https://github.com/dzerik/ha-sberhome/pull/85), ответ в issue опубликован. Реальный домашний режим не переключался; группы/расписания — отдельный оставшийся scope |
| [#61: проверка API](https://github.com/dzerik/ha-sberhome/issues/61) | [Анализ](research/2026-11-04-issue-61-api-contracts.md) отделяет моки от живых наблюдений. OpenSpec сохранности TIME подготовлен; живые A/B-контроли подтвердили удаление/перенос и независимость двух TIME. Последний триггер отклонён HTTP 500 | [Change](changes/preserve-scenario-schedules/proposal.md), [результаты](changes/preserve-scenario-schedules/validation.md). Все временные объекты удалены. Реализация не начата; прочие URL/методы остаются неподтверждёнными |
| [#60: SmartApp → HA](https://github.com/dzerik/ha-sberhome/issues/60) | Предложена отдельная opt-in функция; в комментарии отмечена ручная регистрация навыка в Studio | Сначала PoC и актуальная проверка SmartApp-протокола, аутентификации webhook и требований к HTTPS; затем отдельное изменение |

Для №61 и №63 результат мок-теста не заменяет проверку в облаке/на устройстве.
Для №78 не переносим URL авторизации из issue в репозиторий: достаточно
описания симптома без параметров сессии.
