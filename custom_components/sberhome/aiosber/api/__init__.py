"""High-level API endpoints by domain.

Каждый класс — обёртка над `HttpTransport` для конкретного домена API
(devices, groups, scenarios, pairing, indicator). Возвращает типизированные
DTO из `aiosber.dto`, маппит ошибки в `aiosber.exceptions`.
"""

from __future__ import annotations

from .devices import DeviceAPI
from .effects import LightEffectsAPI
from .groups import GroupAPI
from .indicator import IndicatorAPI
from .inventory import InventoryAPI
from .pairing import PairingAPI
from .scenario_templates import ScenarioTemplatesAPI
from .scenarios import ScenarioAPI

__all__ = [
    "DeviceAPI",
    "GroupAPI",
    "IndicatorAPI",
    "InventoryAPI",
    "LightEffectsAPI",
    "PairingAPI",
    "ScenarioAPI",
    "ScenarioTemplatesAPI",
]
