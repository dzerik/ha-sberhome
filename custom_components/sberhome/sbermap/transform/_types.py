"""Типы для transform layer — typed HA-сущности.

Гибридный режим: используем HA enum'ы (`Platform`, `*DeviceClass`) для
type safety. См. CLAUDE.md → "Архитектурная парадигма" → "Гибридный sbermap".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.const import Platform


@dataclass(slots=True, frozen=True)
class HaEntityData:
    """Описание HA-сущности после трансформации Sber→HA.

    Привязана к одному Platform. Если устройство Sber создаёт несколько
    HA-entities (socket = switch + 3 sensor'а), `sber_to_ha()` возвращает
    list[HaEntityData].

    Args:
        platform: HA-platform (Platform.LIGHT, Platform.SWITCH, ...).
        unique_id: уникальный ID для HA entity registry.
        name: display name.
        state: HA-state value (STATE_ON/STATE_OFF для on_off, sensor measurement,
            HVACMode.* для climate, и т.п.).
        attributes: полный набор HA attributes (brightness, hs_color, и т.п.).
        device_class: optional device_class enum (для sensor/binary_sensor/cover).
        unit_of_measurement: для sensor'ов (UnitOfTemperature.CELSIUS, и т.п.).
        sber_category: оригинальная Sber-категория (для трассировки).
        state_attribute_key: ключ Sber-feature, в котором лежит состояние сущности
            (для NUMBER/SELECT/EXTRA_SWITCH; для primary on_off — None).
        entity_category: HA EntityCategory ("config" | "diagnostic" | None).
        icon: mdi-иконка ("mdi:lock", и т.п.).
        options: tuple options для SELECT.
        min_value/max_value/step: диапазон для NUMBER.
        scale: множитель raw → value (для NUMBER, e.g. 0.001 для мА → А).
        enabled_by_default: визуально включена ли сущность по умолчанию.
        suggested_display_precision: число знаков после запятой для SENSOR.
        event_types: tuple подтипов события для EVENT (e.g. ("click", "double_click")).
        state_class: SensorStateClass.MEASUREMENT/None для SENSOR.
        command_value: для BUTTON — что подставить в desired_state[key].enum_value
            при нажатии (None ⇒ просто bool_value=True).
    """

    platform: Platform
    unique_id: str
    name: str
    state: Any
    attributes: dict[str, Any] = field(default_factory=dict)
    device_class: Any | None = None
    unit_of_measurement: str | None = None
    sber_category: str | None = None
    state_attribute_key: str | None = None
    entity_category: Any | None = None
    icon: str | None = None
    options: tuple[str, ...] | None = None
    min_value: float | None = None
    max_value: float | None = None
    step: float | None = None
    scale: float = 1.0
    enabled_by_default: bool = True
    suggested_display_precision: int | None = None
    event_types: tuple[str, ...] | None = None
    state_class: Any | None = None
    command_value: str | None = None
