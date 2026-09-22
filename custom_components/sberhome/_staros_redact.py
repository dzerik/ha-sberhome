"""Редакция сырого дампа настроек колонок перед шерингом.

Дамп (кнопка «Дамп настроек» в модалке колонки) предназначен для приложения к
issue, поэтому из него вычищаются идентификаторы устройства и сети. Структура
настроек (типы узлов, id, значения тумблеров/слайдеров, опции) остаётся —
ради неё дамп и нужен. Живёт в HA-слое: это диагностическая политика адаптера,
не бизнес-логика ядра.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "**REDACTED**"

# COPY-узлы дерева /v18, чей `value` — идентификатор устройства.
_SECRET_NODE_IDS = frozenset(
    {
        "deviceData",
        "deviceId",
        "publicSerialNumber",
        "publicSerialNumberV2",
        "serialNumber",
        "macAddress",
        "ipAddress",
    }
)
# Узлы, чьё значение может содержать имя Wi-Fi сети.
_WIFI_NODE_IDS = frozenset({"wifi_change", "wifiSsid", "ssid"})
_VALUE_KEYS = ("value", "checked")

# Идентификаторы в произвольных строковых значениях.
_MAC_RE = re.compile(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_LONG_HEX_RE = re.compile(r"\b[0-9a-fA-F]{24,}\b")  # device id вида 472502d6…


def _redact_str(value: str) -> str:
    """Замаскировать MAC/IP/длинный hex-идентификатор в строке."""
    value = _MAC_RE.sub(REDACTED, value)
    value = _IP_RE.sub(REDACTED, value)
    return _LONG_HEX_RE.sub(REDACTED, value)


def _redact_node(node: Any) -> Any:
    """Рекурсивно очистить узел дерева (dict/list/str) от идентификаторов."""
    if isinstance(node, dict):
        node_id = node.get("id")
        redact_value = node_id in _SECRET_NODE_IDS or node_id in _WIFI_NODE_IDS
        out: dict[str, Any] = {}
        for key, val in node.items():
            if redact_value and key in _VALUE_KEYS:
                out[key] = REDACTED
            else:
                out[key] = _redact_node(val)
        return out
    if isinstance(node, list):
        return [_redact_node(item) for item in node]
    if isinstance(node, str):
        return _redact_str(node)
    return node


def redact_staros_tree(tree: Any) -> Any:
    """Очистить сырое дерево настроек колонки от идентификаторов устройства/сети.

    Возвращает НОВУЮ структуру (исходную не мутирует). Значения настроек
    (тумблеры/слайдеры/опции), типы и id узлов сохраняются.
    """
    return _redact_node(tree)


__all__ = ["REDACTED", "redact_staros_tree"]
