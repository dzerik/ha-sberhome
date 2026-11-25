# manual-reauth Specification

## Purpose
Принудительный повторный вход с очисткой всех локальных credentials записи
Сбер ID или SMS и обоих API-каналов, с сохранением аккаунта, устройств и настроек.

## Requirements

### Requirement: Explicit reset with confirmation
Интеграция SHALL предлагать отдельный пункт сброса авторизации в параметрах HA.
Подтверждение SHALL объяснять временную недоступность до повторного входа.

#### Scenario: Cancel before confirmation
- **WHEN** пользователь закрывает подтверждение
- **THEN** токены, подключение и параметры записи остаются прежними

### Requirement: Complete local credential reset
При подтверждении интеграция SHALL успешно остановить запись до очистки,
удалить все наборы токенов Сбер ID, SMS, gateway и companion settings,
а также закрыть незавершённые входы этой записи. Ошибка остановки SHALL
оставлять сохранённые данные авторизации без изменений.

#### Scenario: Reset either login method
- **WHEN** пользователь подтверждает сброс записи Сбер ID или SMS
- **THEN** все локальные credential payloads этой записи удалены
- **AND** начат свежий штатный reauth тем же способом
- **AND** запись, unique_id, параметры, device/entity registry и другие записи сохранены

#### Scenario: Late refresh from the old session
- **WHEN** старый token store пытается сохранить, прочитать или очистить токены после сброса
- **THEN** он не читает и не изменяет credentials нового поколения

#### Scenario: Legacy account identity is missing
- **WHEN** у старой записи нет unique_id
- **THEN** до очистки идентификатор аккаунта восстанавливается из прежних credentials
- **AND** если определить аккаунт невозможно, сброс отклонён без удаления данных

#### Scenario: Old login finishes after reset
- **WHEN** незавершённый старый вход заканчивается после очистки
- **THEN** он не записывает свои токены в запись

### Requirement: Recover through normal reauthentication
Повторный вход SHALL обновлять ту же запись и проверять прежний аккаунт.
После перезапуска HA до входа интеграция SHALL снова предлагать reauth,
не пытаясь использовать удалённые credentials.

#### Scenario: Same account signs in again
- **WHEN** свежий reauth завершён прежним аккаунтом
- **THEN** запись перезагружается с новыми credentials без сброса пользовательских настроек

#### Scenario: Different account attempts sign-in
- **WHEN** пользователь вводит другой аккаунт при reauth
- **THEN** вход отклонён с wrong_account и новая запись не создаётся
