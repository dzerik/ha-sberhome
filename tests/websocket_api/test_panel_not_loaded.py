"""Панель, пока запись не загружена: понятный ответ, а не внутренняя ошибка.

Облако недоступно при запуске — запись ждёт повторной настройки, а панель уже
открыта (команды регистрируются до первого опроса). Каждая команда должна
ответить «интеграция не загружена» или пустым результатом, а не упасть на
отсутствующем координаторе.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

import custom_components.sberhome.websocket_api as ws_pkg

from ..fake_cloud import FakeSberCloud
from .conftest import Panel

_SPEC = {"name": "Сценарий", "phrases": ["привет"], "actions": []}

FIELDS: dict[str, dict[str, Any]] = {
    "device_write_schema": {"device_id": "d"},
    "device_detail": {"device_id": "d"},
    "refetch_device": {"device_id": "d"},
    "diagnose_device": {"device_id": "d"},
    "set_device_area": {"device_id": "d", "area_id": None},
    "set_enabled": {"device_ids": ["d"]},
    "toggle_device": {"device_id": "d", "enabled": True},
    "rename_room": {"room_id": "r", "name": "Зал"},
    "pairing/start": {"pairing_type": "wifi"},
    "intents/get": {"intent_id": "i"},
    "intents/create": {"spec": _SPEC},
    "intents/update": {"intent_id": "i", "spec": _SPEC},
    "intents/delete": {"intent_id": "i"},
    "intents/test": {"intent_id": "i"},
    "update_settings": {"settings": {}},
    "import_config": {"config": {}},
    "inject_ws_message": {"payload": {}},
    "replay_ws_message": {"payload": {}},
    "tts_surrogate/ensure": {"home_id": "h"},
    "tts_surrogate/test": {"home_id": "h", "message": "m"},
    "ttc_surrogate/ensure": {"home_id": "h"},
    "ttc_surrogate/test": {"home_id": "h", "message": "m"},
}
"""Обязательные поля команд; остальные команды полей не требуют."""

EMPTY_RESULTS: dict[str, dict[str, Any]] = {
    "listeners/list": {"listeners": []},
    "tts_surrogate/status": {"homes": []},
    "ttc_surrogate/status": {"homes": []},
    "tts_surrogate/ensure": {"ok": False, "error": "integration not loaded"},
    "tts_surrogate/test": {"ok": False, "error": "integration not loaded"},
    "ttc_surrogate/ensure": {"ok": False, "error": "integration not loaded"},
    "ttc_surrogate/test": {"ok": False, "error": "integration not loaded"},
}
"""Команды, отвечающие пустым результатом вместо ошибки ``not_loaded``."""

COMMANDS = sorted(command._ws_command.removeprefix("sberhome/") for command in ws_pkg._COMMANDS)


@pytest.mark.parametrize("command", COMMANDS)
async def test_command_answers_while_entry_waits_for_cloud(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    panel: Panel,
    command: str,
) -> None:
    fake_cloud.down = True
    entry = await setup_sberhome(options={})
    assert entry.state is ConfigEntryState.SETUP_RETRY
    requests_before = len(fake_cloud.requests)

    response = await panel(command, **FIELDS.get(command, {}))

    if command in EMPTY_RESULTS:
        assert response["success"], response
        assert response["result"] == EMPTY_RESULTS[command]
    else:
        assert response["success"] is False, response
        assert response["error"]["code"] == "not_loaded"
    # Без координатора команда не ходит в облако.
    assert len(fake_cloud.requests) == requests_before
