"""Настройки, которые панель и форма параметров меняют без перезагрузки.

Единое место для типов, диапазонов и значений по умолчанию: WS-команды
панели, форма параметров и координатор читают отсюда. Раньше диапазон
интервала опроса был продублирован и разошёлся (300 против 3600 секунд),
а размеры буферов DevTools и таймаут команд были зашиты в код.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from .const import (
    CONF_COMMAND_TIMEOUT,
    CONF_DEVTOOLS_BUFFER_SIZE,
    CONF_SCAN_INTERVAL,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_DEVTOOLS_BUFFER_SIZE,
    DEFAULT_SCAN_INTERVAL,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)


def _strict_int(value: Any) -> int:
    """Целое без приведения строк и bool."""
    if not isinstance(value, int) or isinstance(value, bool):
        raise vol.Invalid("expected an integer")
    return value


def _strict_number(value: Any) -> float:
    """Число (int/float) без приведения строк и bool."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise vol.Invalid("expected a number")
    return float(value)


SETTINGS_DEFAULTS: dict[str, Any] = {
    CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    CONF_DEVTOOLS_BUFFER_SIZE: DEFAULT_DEVTOOLS_BUFFER_SIZE,
    CONF_COMMAND_TIMEOUT: DEFAULT_COMMAND_TIMEOUT,
}
"""Значения по умолчанию для каждой настройки."""

SETTINGS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SCAN_INTERVAL): vol.All(
            _strict_int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
        vol.Optional(CONF_DEVTOOLS_BUFFER_SIZE): vol.All(_strict_int, vol.Range(min=10, max=5000)),
        vol.Optional(CONF_COMMAND_TIMEOUT): vol.All(_strict_number, vol.Range(min=1, max=120)),
    },
    extra=vol.REMOVE_EXTRA,
)
"""Проверка значений: неверный тип или диапазон отклоняет запрос целиком."""


def _limits(schema: vol.Schema) -> dict[str, dict[str, float]]:
    limits: dict[str, dict[str, float]] = {}
    for key, validator in schema.schema.items():
        for part in getattr(validator, "validators", ()):
            if isinstance(part, vol.Range):
                limits[str(key)] = {"min": part.min, "max": part.max}
    return limits


SETTINGS_LIMITS: dict[str, dict[str, float]] = _limits(SETTINGS_SCHEMA)
"""Границы из :data:`SETTINGS_SCHEMA` — панель строит поля по ним, а не по копии."""

LIVE_SETTINGS: frozenset[str] = frozenset(SETTINGS_DEFAULTS)
"""Ключи, смена которых применяется на лету, без перезагрузки записи."""


def read_settings(options: Mapping[str, Any]) -> dict[str, Any]:
    """Текущие настройки из ``entry.options`` с подставленными умолчаниями."""
    return {key: options.get(key, default) for key, default in SETTINGS_DEFAULTS.items()}


def only_live_settings_changed(before: Mapping[str, Any], after: Mapping[str, Any]) -> bool:
    """True, если между снимками параметров поменялись только живые настройки.

    Args:
        before: Параметры записи до изменения.
        after: Параметры после изменения.

    Returns:
        ``False`` и при отсутствии изменений, и если затронут любой другой ключ
        (например, выбор устройств — он требует перезагрузки).
    """
    changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
    return bool(changed) and changed <= LIVE_SETTINGS
