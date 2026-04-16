"""TypedDevice — базовый wrapper над `DeviceDto`.

Идея: `DeviceDto` — универсальный raw-DTO с `reported_state: list[AttributeValueDto]`.
`TypedDevice` — более удобный API с типизированными свойствами под конкретную
категорию устройства (`LightDevice.is_on`, `LightDevice.brightness`).

Это **read-only view** поверх `DeviceDto` — typed accessors для частых полей.
Команды (set_state) не методы устройства, а действия `DeviceAPI` (т.к. требуют
HttpTransport). Это согласуется с CLAUDE.md → "DTO без бизнес-логики".

Использование:

    devices = await client.devices.list()
    typed = [as_typed(d) for d in devices]
    for t in typed:
        if isinstance(t, LightDevice) and t.is_on:
            print(f"{t.name}: brightness={t.brightness}")
"""

from __future__ import annotations

from typing import Any

from ..._generated.feature_types import FEATURE_TYPES
from ..device import DeviceDto


class TypedDevice:
    """Базовый class — обёртка над `DeviceDto` с typed accessors.

    Подклассы добавляют свойства под features конкретной категории.
    """

    # Категории, для которых этот wrapper применим.
    # Подклассы переопределяют. Используется в `as_typed()` для диспетчеризации.
    CATEGORIES: tuple[str, ...] = ()

    __slots__ = ("_dto",)

    def __init__(self, dto: DeviceDto) -> None:
        self._dto = dto

    # ----- Прокси к DeviceDto -----
    @property
    def dto(self) -> DeviceDto:
        """Доступ к raw DeviceDto (для редких случаев когда typed properties недостаточно)."""
        return self._dto

    @property
    def id(self) -> str | None:
        return self._dto.id

    @property
    def name(self) -> str | None:
        return self._dto.name

    @property
    def category(self) -> str | None:
        """Категория из `image_set_type` / `device_type_name`."""
        return self._dto.image_set_type or self._dto.device_type_name

    @property
    def model(self) -> str | None:
        return self._dto.device_info.model if self._dto.device_info else None

    @property
    def serial_number(self) -> str | None:
        return self._dto.serial_number

    @property
    def sw_version(self) -> str | None:
        return self._dto.sw_version

    # ----- Универсальные свойства из reported_state -----
    @property
    def online(self) -> bool | None:
        """`online` обязательное поле для всех категорий."""
        return self._reported_bool("online")

    @property
    def battery_percentage(self) -> int | None:
        return self._reported_int("battery_percentage")

    @property
    def battery_low(self) -> bool | None:
        return self._reported_bool("battery_low_power")

    @property
    def signal_strength(self) -> int | str | None:
        """Может быть INTEGER (dBm) или ENUM (low/medium/high)."""
        v = self._dto.reported_value("signal_strength")
        return v

    # ----- Internal helpers -----
    def _reported_value(self, key: str) -> Any:
        return self._dto.reported_value(key)

    def _reported_bool(self, key: str) -> bool | None:
        v = self._reported_value(key)
        return bool(v) if v is not None else None

    def _reported_int(self, key: str) -> int | None:
        v = self._reported_value(key)
        return int(v) if v is not None else None

    def _reported_float(self, key: str) -> float | None:
        v = self._reported_value(key)
        return float(v) if v is not None else None

    def _reported_str(self, key: str) -> str | None:
        v = self._reported_value(key)
        return str(v) if v is not None else None

    # ----- Discovery -----
    def has_feature(self, key: str) -> bool:
        """Поддерживает ли устройство feature (есть ли в reported_state)."""
        return self._dto.reported(key) is not None

    def feature_type(self, key: str) -> str | None:
        """Wire-тип feature (BOOL/INTEGER/ENUM/...) из spec."""
        return FEATURE_TYPES.get(key)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(id={self.id!r}, name={self.name!r}, online={self.online})"
