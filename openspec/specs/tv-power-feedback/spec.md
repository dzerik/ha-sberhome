# tv-power-feedback Specification

## Purpose
Достоверность состояния питания TV и доступность штатных команд включения
и выключения Home Assistant при неподтверждённой обратной связи.

## Requirements

### Requirement: Достоверность питания TV

TV power с epoch reported timestamp 1970/0001 либо без BOOL значения SHALL
отображаться как unknown и assumed. Неподтверждённый desired без timestamp
SHALL NOT выдавать фактическое питание. Подтверждённый BOOL и legacy BOOL
без метки SHALL сохранять on/off.

#### Scenario: Дамп Salute TV из №95
- **WHEN** reported on_off=false имеет epoch, а desired=true не имеет timestamp
- **THEN** HA state равен unknown, assumed_state=true

#### Scenario: Подтверждение питания
- **WHEN** после unknown приходит reported BOOL с реальным timestamp
- **THEN** HA показывает on/off и снимает assumed_state

#### Scenario: Команда в пути
- **WHEN** свежий desired отличается от подтверждённого reported
- **THEN** отображаемое desired состояние помечено assumed
- **AND** совпадающий desired не меняет достоверность reported

### Requirement: Доступность явных команд питания

Неизвестный статус SHALL сохранять TURN_ON/TURN_OFF и assumed_state,
необходимые штатному HA для отдельных power controls. Явные сервисы SHALL
отправлять BOOL true/false правильному устройству независимо от power state.

#### Scenario: Включить и выключить без подтверждения
- **WHEN** TV остаётся unknown после включения и вызывается turn_off
- **THEN** отправляется on_off=false, а не повторное включение

### Requirement: Сохранение availability и ошибок

Недоступность TV и cloud rejection SHALL сохранять обычное поведение HA,
не подменяя connectivity предположением о включённом устройстве.

#### Scenario: Offline
- **WHEN** reported online=false
- **THEN** media_player становится unavailable

#### Scenario: Команда отклонена
- **WHEN** облако отклоняет turn_off
- **THEN** сервис HA сообщает ошибку
