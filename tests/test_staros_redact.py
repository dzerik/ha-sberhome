"""Тесты редакции сырого дампа настроек колонки (для шеринга в issue)."""

from __future__ import annotations

from custom_components.sberhome._staros_redact import REDACTED, redact_staros_tree


def test_masks_device_identifier_copy_nodes():
    tree = {
        "settings": [
            {"type": "COPY", "id": "deviceId", "value": "472502d68000000e425200001db64461"},
            {"type": "COPY", "id": "publicSerialNumberV2", "value": "SXY31R05VD000181"},
            {"type": "COPY", "id": "firmwareNumber", "value": "1.105.14"},
        ]
    }
    out = redact_staros_tree(tree)
    assert out["settings"][0]["value"] == REDACTED
    assert out["settings"][1]["value"] == REDACTED
    assert out["settings"][2]["value"] == "1.105.14"  # версия ПО — не секрет


def test_keeps_setting_structure_and_values():
    tree = {
        "settings": [
            {"type": "TOGGLE", "id": "assistant_sounds_enabled", "title": "Звук", "enabled": True},
            {
                "type": "RADIO_BUTTONS",
                "id": "led_equalizer_settings",
                "checked": "3600",
                "radioButtons": [{"value": "3600"}, {"value": "30"}, {"value": "0"}],
            },
            {"type": "SLIDER", "id": "LedBrightness", "value": 50, "min": 10, "max": 100},
        ]
    }
    out = redact_staros_tree(tree)
    assert out["settings"][0]["enabled"] is True
    assert out["settings"][0]["title"] == "Звук"
    assert out["settings"][1]["checked"] == "3600"  # значение radio — не секрет
    assert [o["value"] for o in out["settings"][1]["radioButtons"]] == ["3600", "30", "0"]
    assert out["settings"][2]["value"] == 50  # обычный слайдер не трогаем


def test_masks_wifi_ssid_node():
    tree = {"settings": [{"type": "CARD", "id": "wifi_change", "value": "MyHomeNet"}]}
    out = redact_staros_tree(tree)
    assert out["settings"][0]["value"] == REDACTED


def test_masks_mac_ip_and_long_hex_in_free_strings():
    tree = {
        "a": "AA:BB:CC:DD:EE:FF",
        "b": "192.168.1.40",
        "c": "472502d68000000e425200001db64461",
        "d": "Кухня",  # обычный текст не трогаем
        "e": 3600,  # числа не трогаем
    }
    out = redact_staros_tree(tree)
    assert out["a"] == REDACTED
    assert out["b"] == REDACTED
    assert out["c"] == REDACTED
    assert out["d"] == "Кухня"
    assert out["e"] == 3600


def test_does_not_mutate_input():
    original = {"settings": [{"id": "deviceId", "value": "472502d68000000e425200001db64461"}]}
    redact_staros_tree(original)
    assert original["settings"][0]["value"] == "472502d68000000e425200001db64461"
