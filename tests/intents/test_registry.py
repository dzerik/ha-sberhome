"""Action registry tests — encode/decode round-trip + extensibility."""

from __future__ import annotations

import pytest

from custom_components.sberhome.intents.registry import (
    ActionRegistration,
    get_action,
    list_actions,
    register_action,
    schema_dict,
)
from custom_components.sberhome.intents.spec import FieldSpec, IntentAction


class TestRegistry:
    def test_default_actions_present(self):
        types = {a.type for a in list_actions()}
        assert types == {"tts", "device_command", "trigger_notify", "ha_event_only"}

    def test_get_action_unknown_returns_none(self):
        assert get_action("not_a_real_type") is None

    def test_schema_dict_is_serialisable(self):
        """schema_dict() returns plain dicts/lists — directly JSON-able for WS."""
        schema = schema_dict()
        # 4 встроенных + кастомные если зарегистрированы (в этом тесте 4).
        assert len(schema) >= 4
        for entry in schema:
            assert isinstance(entry["type"], str)
            assert isinstance(entry["ui_label"], str)
            assert isinstance(entry["fields"], list)


class TestEncodeDecodeTts:
    def test_round_trip(self):
        action = IntentAction(
            type="tts",
            data={"phrase": "Включаю кофе", "device_ids": ["sb-1", "sb-2"]},
        )
        reg = get_action("tts")
        assert reg is not None
        tasks = reg.encode(action.data)
        assert len(tasks) == 1
        assert tasks[0]["type"] == "PRONOUNCE_COMMAND"
        assert tasks[0]["pronounce_data"]["phrase"] == "Включаю кофе"
        # decode обратно
        decoded, leftover = reg.decode(tasks)
        assert leftover == []
        assert decoded == action

    def test_encode_skips_invalid(self):
        """Без phrase или device_ids — пустой list (UI ловит до encode'а
        через required=True, но защита на случай неполного payload'а)."""
        reg = get_action("tts")
        assert reg.encode({"phrase": "X", "device_ids": []}) == []
        assert reg.encode({"phrase": "", "device_ids": ["a"]}) == []

    def test_decode_unrelated_tasks_passes_through(self):
        reg = get_action("tts")
        tasks = [{"type": "DEVICE_COMMAND", "device_command_data": {}}]
        decoded, leftover = reg.decode(tasks)
        assert decoded is None
        assert leftover == tasks


class TestEncodeDecodeDeviceCommand:
    def test_round_trip(self):
        action = IntentAction(
            type="device_command",
            data={
                "device_id": "lamp-1",
                "attributes": [{"key": "on_off", "type": "BOOL", "bool_value": True}],
            },
        )
        reg = get_action("device_command")
        tasks = reg.encode(action.data)
        assert tasks[0]["device_command_data"]["device_id"] == "lamp-1"
        decoded, leftover = reg.decode(tasks)
        assert leftover == []
        assert decoded == action


class TestEncodeDecodeTriggerNotify:
    def test_round_trip(self):
        reg = get_action("trigger_notify")
        tasks = reg.encode({})
        assert tasks == [{"type": "TRIGGER_NOTIFY_COMMAND"}]
        decoded, _ = reg.decode(tasks)
        assert decoded == IntentAction(type="trigger_notify")


class TestEncodeDecodeHaEventOnly:
    def test_empty_tasks_decodes_to_event_only(self):
        reg = get_action("ha_event_only")
        decoded, leftover = reg.decode([])
        assert decoded == IntentAction(type="ha_event_only")
        assert leftover == []

    def test_non_empty_tasks_passes_through(self):
        reg = get_action("ha_event_only")
        tasks = [{"type": "PRONOUNCE_COMMAND"}]
        decoded, leftover = reg.decode(tasks)
        assert decoded is None
        assert leftover == tasks


class TestExtensibility:
    """Adding custom action types — proves the registry is extensible
    without modifying existing code."""

    def test_register_custom_action(self):
        custom = ActionRegistration(
            type="my_custom_action",
            ui_label="Мой action",
            ui_fields=(FieldSpec(key="x", type="text", label="X"),),
            encode=lambda d: [{"type": "FUTURE_TASK", "x": d.get("x")}],
            decode=lambda tasks: (
                (IntentAction(type="my_custom_action", data={"x": tasks[0].get("x")}), [])
                if tasks and tasks[0].get("type") == "FUTURE_TASK"
                else (None, tasks)
            ),
        )
        register_action(custom)

        try:
            assert get_action("my_custom_action") is not None
            tasks = custom.encode({"x": "test"})
            assert tasks == [{"type": "FUTURE_TASK", "x": "test"}]
            decoded, _ = custom.decode(tasks)
            assert decoded.type == "my_custom_action"
            assert decoded.data == {"x": "test"}
        finally:
            # cleanup, чтобы не утекало в другие тесты
            from custom_components.sberhome.intents import registry as reg_module

            reg_module._REGISTRY.pop("my_custom_action", None)


@pytest.mark.parametrize(
    "action_type", ["tts", "device_command", "trigger_notify", "ha_event_only"]
)
def test_default_actions_have_stable_metadata(action_type):
    """Защита от случайного rename'а type'а — это нарушит persisted IntentSpec'ы."""
    reg = get_action(action_type)
    assert reg is not None
    assert reg.type == action_type
    assert reg.ui_label  # не пустой
