# aiosber CLI examples

Standalone-скрипты, демонстрирующие использование `aiosber` без Home Assistant.

Эти примеры показывают, как `aiosber` работает как обычная Python-библиотека —
ровно то, чем она станет после extract в свой PyPI-пакет (см. CLAUDE.md → 2.0.0).

## Запуск

```bash
# Из корня репо. PYTHONPATH нужен пока aiosber живёт внутри custom_components/.
PYTHONPATH=custom_components/sberhome python examples/list_devices.py
```

После 2.0.0 будет просто `pip install aiosber`, и:

```bash
python examples/list_devices.py
```

## Скрипты

- **`list_devices.py`** — авторизация через PKCE + список всех устройств.
- **`set_color.py`** — изменение цвета лампы через `DeviceAPI.set_state`.
- **`ws_listen.py`** — подписка на real-time DEVICE_STATE через WebSocket.

## Установка зависимостей

```bash
pip install httpx websockets
```
