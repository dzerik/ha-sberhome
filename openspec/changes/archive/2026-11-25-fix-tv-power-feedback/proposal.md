# Proposal

## Why

[№95](https://github.com/dzerik/ha-sberhome/issues/95): Salute TV включается,
но reported on_off=false с epoch-меткой удерживает HA в состоянии off.
Повторное нажатие штатного power control снова включает устройство.
Команды TURN_ON/TURN_OFF уже реализованы; дефект в достоверности состояния
и выборе контролов HA.

## What Changes

- Неинициализированное или отсутствующее питание TV отображается unknown.
- assumed_state включает отдельные штатные on/off controls HA.
- Отличающийся свежий desired остаётся предположением, а не подтверждением.
- Подтверждённые значения, IDs, availability и команды сохраняют поведение.

## Capabilities

### New Capabilities

- tv-power-feedback: достоверность питания и доступность штатных команд TV.

### Modified Capabilities

Нет.

## Impact

Три модуля HA mapping/adapter, регрессии HA/FakeCloud. Новые сущности,
endpoint, dependencies и собственные строки локализации не добавляются.
Проверка фактического исполнения команд на Salute TV остаётся за автором issue.
