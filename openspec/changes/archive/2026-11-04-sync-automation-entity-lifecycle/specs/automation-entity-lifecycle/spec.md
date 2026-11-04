## ADDED Requirements

### Requirement: Сохранность service registry

Maintenance SHALL сохранять общий service device групп при успешных опросах,
не удаляя существующие entity_id и пользовательские настройки.

#### Scenario: Неизменный инвентарь
- **WHEN** выполняются повторные успешные полные опросы с неизменной GROUP
- **THEN** service device и сущность группы остаются зарегистрированы

### Requirement: Динамическое обнаружение

Новые home/active/group switch SHALL появляться без reload, один раз на cloud ID.
Listener discovery SHALL сниматься при unload.

#### Scenario: Новый сценарий и группа
- **WHEN** после setup авторитетный инвентарь содержит новый сценарий и непустую GROUP
- **THEN** их переключатели появляются без перезапуска
- **AND** повторные уведомления не добавляют дубли

### Requirement: Имена и идентичность

Исходные имена automation entities SHALL следовать авторитетному инвентарю,
сохраняя unique_id, entity_id, custom name и disabled_by пользователя.

#### Scenario: Переименование сценария
- **WHEN** cloud-сценарий переименован
- **THEN** исходные имена run/stop/cancel/active обновляются на пяти языках
- **AND** пользовательское имя и идентификаторы HA сохраняются

### Requirement: Отсутствие и возврат объекта

Удалённые home/scenario/group и пустые либо сменившие тип GROUP SHALL быть
unavailable без удаления registry. Возврат same ID SHALL восстанавливать сущность.

#### Scenario: Orphan membership
- **WHEN** GROUP отсутствует, но устройство ещё содержит её ID
- **THEN** переключатель группы недоступен

#### Scenario: Пустая группа
- **WHEN** ранее зарегистрированная GROUP теряет последнего участника и затем получает его снова
- **THEN** сущность становится unavailable и возвращается с прежним entity_id

### Requirement: Актуальный список домов

Успешное обновление home inventory SHALL обновлять homes и перечитываемые at_home.
Ошибка SHALL сохранять последний подтверждённый список.

#### Scenario: Второй дом
- **WHEN** успешное обновление возвращает новый дом после setup
- **THEN** он получает at_home switch без перезапуска

### Requirement: Обновление групп по участникам

Изменение reported state любого участника SHALL обновлять HA state группы,
сохраняя пользовательский выбор отдельных device entities и расписание polling.

#### Scenario: Невыбранный участник
- **WHEN** приходит DEVICE_STATE невыбранного для отдельной HA-сущности участника GROUP
- **THEN** состояние группы отражает новое reported значение
- **AND** отдельная device entity не создаётся
