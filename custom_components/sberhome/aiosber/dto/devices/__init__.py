"""Типизированные wrappers для DeviceDto.

Каждая категория устройств Sber имеет свой подкласс `TypedDevice` с typed
accessors под её features. Используется для better DX (IDE autocomplete,
type checking) и для документации API.

Использование:

    from custom_components.sberhome.aiosber.dto.devices import as_typed, LightDevice

    devices = await client.devices.list()
    for d in devices:
        typed = as_typed(d)
        if isinstance(typed, LightDevice) and typed.is_on:
            print(f"{typed.name}: brightness={typed.brightness}")

Все 28 категорий из `sber_full_spec.json` имеют свой класс.
"""

from __future__ import annotations

from ..device import DeviceDto
from ._base import TypedDevice
from .appliances import KettleDevice, TvDevice, VacuumDevice
from .covers import (
    CurtainDevice,
    GateDevice,
    ValveDevice,
    WindowBlindDevice,
)
from .electric import RelayDevice, SocketDevice
from .hvac import (
    AirConditionerDevice,
    AirPurifierDevice,
    BoilerDevice,
    FanDevice,
    HeaterDevice,
    HumidifierDevice,
    RadiatorDevice,
    UnderfloorHeatingDevice,
)
from .lights import LedStripDevice, LightDevice
from .misc import HubDevice, IntercomDevice, ScenarioButtonDevice
from .sensors import (
    DoorSensorDevice,
    GasSensorDevice,
    MotionSensorDevice,
    SmokeSensorDevice,
    TemperatureSensorDevice,
    WaterLeakSensorDevice,
)

# Auto-built reverse map — все подклассы TypedDevice с CATEGORIES.
# Добавление нового класса (например MatterPlugDevice) — просто declare с
# CATEGORIES = ("...",), он автоматически попадёт сюда.
_ALL_TYPED_CLASSES: tuple[type[TypedDevice], ...] = (
    LightDevice,
    LedStripDevice,
    SocketDevice,
    RelayDevice,
    TemperatureSensorDevice,
    WaterLeakSensorDevice,
    DoorSensorDevice,
    MotionSensorDevice,
    SmokeSensorDevice,
    GasSensorDevice,
    CurtainDevice,
    WindowBlindDevice,
    GateDevice,
    ValveDevice,
    AirConditionerDevice,
    HeaterDevice,
    RadiatorDevice,
    BoilerDevice,
    UnderfloorHeatingDevice,
    FanDevice,
    AirPurifierDevice,
    HumidifierDevice,
    KettleDevice,
    VacuumDevice,
    TvDevice,
    ScenarioButtonDevice,
    IntercomDevice,
    HubDevice,
)


_CATEGORY_TO_CLASS: dict[str, type[TypedDevice]] = {}
for _cls in _ALL_TYPED_CLASSES:
    for _cat in _cls.CATEGORIES:
        _CATEGORY_TO_CLASS[_cat] = _cls


def as_typed(dto: DeviceDto) -> TypedDevice:
    """Превратить `DeviceDto` в специфичный wrapper по `image_set_type`.

    Если категория устройства неизвестна (например новая, ещё не добавленная),
    возвращается базовый `TypedDevice` с минимальным набором свойств.

    Resolve порядок:
    1. Точное совпадение `image_set_type` → класс.
    2. Substring match (для image типов с префиксами/суффиксами):
       `bulb_sber` → содержит `bulb_sber` → ... (текущий маппинг
       не делает substring — для надёжности можно расширить).
    3. Fallback — базовый `TypedDevice`.
    """
    image = dto.image_set_type or dto.device_type_name or ""
    cls = _CATEGORY_TO_CLASS.get(image)
    if cls is None:
        # Substring — на случай если `image_set_type` имеет префикс
        # (например `dt_socket_sber` → `socket`).
        for cat, c in _CATEGORY_TO_CLASS.items():
            if cat in image:
                cls = c
                break
    if cls is None:
        return TypedDevice(dto)
    return cls(dto)


def class_for_category(category: str) -> type[TypedDevice] | None:
    """Получить class для конкретной категории (без instance)."""
    return _CATEGORY_TO_CLASS.get(category)


def all_categories() -> frozenset[str]:
    """Все категории, для которых есть typed wrapper."""
    return frozenset(_CATEGORY_TO_CLASS.keys())


__all__ = [
    "AirConditionerDevice",
    "AirPurifierDevice",
    "BoilerDevice",
    "CurtainDevice",
    "DoorSensorDevice",
    "FanDevice",
    "GasSensorDevice",
    "GateDevice",
    "HeaterDevice",
    "HubDevice",
    "HumidifierDevice",
    "IntercomDevice",
    "KettleDevice",
    "LedStripDevice",
    "LightDevice",
    "MotionSensorDevice",
    "RadiatorDevice",
    "RelayDevice",
    "ScenarioButtonDevice",
    "SmokeSensorDevice",
    "SocketDevice",
    "TemperatureSensorDevice",
    "TvDevice",
    "TypedDevice",
    "UnderfloorHeatingDevice",
    "ValveDevice",
    "VacuumDevice",
    "WaterLeakSensorDevice",
    "WindowBlindDevice",
    "all_categories",
    "as_typed",
    "class_for_category",
]
