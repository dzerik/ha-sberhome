# Proposal

## Why

[№62](https://github.com/dzerik/ha-sberhome/issues/62): automation entities
существуют, но общий service device групп ошибочно удаляется maintenance,
новые switch не обнаруживаются, имена и список домов устаревают.
[Исследование](../../../research/2026-11-04-issue-62-entity-lifecycle.md)
содержит воспроизведения на настоящем тестовом HA и FakeCloud.

## What Changes

- Защита общего identifier groups от ошибочного prune.
- Динамическое обнаружение home/active/group switch без дублей и утечек listeners.
- Актуальные исходные имена сценариев, control-кнопок, домов и групп;
  entity_id, unique_id и пользовательские overrides сохраняются.
- Актуальный инвентарь домов, unavailable для удалённых/пустых/сменивших тип групп.
- Уведомление групп при push невыбранного участника без раскрытия его device entities.

## Capabilities

### New Capabilities

- automation-entity-lifecycle: синхронизация существующих automation entities.

### Modified Capabilities

Нет.

## Impact

HA adapters switch/button, coordinator и registry maintenance; регрессии
через HA registry/FakeCloud. Существующие endpoints, bulk-агрегация reported,
desired optimistic semantics и выбор устройств не меняются.
Новые протоколы и команды настоящим устройствам не требуются.
