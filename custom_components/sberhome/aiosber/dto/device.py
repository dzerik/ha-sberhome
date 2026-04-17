"""Top-level device DTOs.

DeviceDto, DeviceInfoDto, ImagesDto, BridgeMeta, CommandDto, IndicatorColor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict
from .enums import ConnectionType, VendorType
from .values import AttributeValueDto


@dataclass(slots=True, frozen=True)
class NameDto:
    """Имя устройства (wire: объект с полями name/default_name/names).

    Wire-формат REST: ``{"name": {"name": "Люстра", "defaultName": "", "names": {}}}``
    Legacy/simplified: ``{"name": "Люстра"}`` (plain string).

    `from_dict` поддерживает оба варианта.
    """

    name: str | None = None
    default_name: str | None = None
    names: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | str | None) -> Self | None:
        if data is None:
            return None
        if isinstance(data, str):
            return cls(name=data)
        if isinstance(data, dict):
            # Wire uses camelCase (defaultName), DTO uses snake_case (default_name).
            if "defaultName" in data and "default_name" not in data:
                data = {**data, "default_name": data.pop("defaultName")}
            return from_dict(cls, data)
        return None

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class DeviceInfoDto:
    """`device_info` поле в DeviceDto."""

    product_id: str | None = None
    model: str | None = None
    matter_node_id: int | None = None
    sub_device_count: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class ImagesDto:
    """Иконки/изображения устройства (URL)."""

    list_on: str | None = None
    list_off: str | None = None
    cards_3d_on: str | None = None
    cards_3d_off: str | None = None
    photo: str | None = None
    bd_list_glyph_1_16_4x: str | None = None
    bd_list_glyph_2_16_4x: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class BridgeMeta:
    """Metadata моста (для Zigbee/Matter — info о хабе-родителе)."""

    code: int | None = None
    message: str | None = None
    matter_node_id: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class CommandDto:
    """Команда, поддерживаемая устройством (из DeviceDto.commands)."""

    key: str | None = None
    state_fields: list[str] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


@dataclass(slots=True, frozen=True)
class IndicatorColor:
    """Цвет LED-индикатора (HSV).

    Wire-поля: id (UUID), hue, saturation, brightness.
    """

    id: str | None = None
    hue: int = 0
    saturation: int = 0
    brightness: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class IndicatorColors:
    default_colors: list[IndicatorColor] = field(default_factory=list)
    current_colors: list[IndicatorColor] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self, omit_none=False)


@dataclass(slots=True, frozen=True)
class DeviceDto:
    """Главный DTO устройства из GET /gateway/v1/devices/.

    Все поля optional кроме `id` (на практике).
    Поле `type` назвали `device_type_name` (точное имя в API).
    """

    id: str | None = None
    name: NameDto | None = None
    device_type_name: str | None = None
    parent_id: str | None = None
    routing_key: str | None = None
    serial_number: str | None = None
    external_id: str | None = None
    group_ids: list[str] | None = None

    device_info: DeviceInfoDto | None = None

    reported_state: list[AttributeValueDto] = field(default_factory=list)
    desired_state: list[AttributeValueDto] = field(default_factory=list)

    correction: dict[str, Any] | None = None  # сырая структура — не разворачиваем
    image_set_type: str | None = None
    images: ImagesDto | None = None

    attributes: list[Any] | None = None  # legacy/extended attributes
    full_categories: list[str] | None = None

    sw_version: str | None = None
    coprocessor_fw_version: str | None = None
    sort_weight_int: int | None = None

    commands: list[CommandDto] | None = None
    children: list[str] | None = None
    linked: list[str] | None = None

    owner_info: dict[str, Any] | None = None  # сырая структура

    connection_type: ConnectionType | None = None
    ip: str | None = None
    mac: str | None = None
    bridge_meta: BridgeMeta | None = None
    landing_id: str | None = None

    # ----- удобные геттеры -----
    @property
    def display_name(self) -> str | None:
        """Человекочитаемое имя устройства (из NameDto или legacy str)."""
        if self.name is None:
            return None
        if isinstance(self.name, str):
            return self.name  # type: ignore[return-value]  # legacy direct construction
        return self.name.name

    def reported(self, key: str) -> AttributeValueDto | None:
        """Найти AttributeValueDto в reported_state по ключу."""
        for av in self.reported_state:
            if av.key == key:
                return av
        return None

    def reported_value(self, key: str) -> Any:
        """Удобный геттер: значение reported по ключу или None."""
        av = self.reported(key)
        return av.value if av is not None else None

    @property
    def vendor(self) -> VendorType | None:
        """Эвристика по device_type_name (sber/sberdevices/tuya)."""
        if not self.device_type_name:
            return None
        name = self.device_type_name.lower()
        for vt in VendorType:
            if vt.value in name:
                return vt
        return None

    # ----- serialization -----
    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        # Pre-process: name может прийти как строка (legacy) или объект (REST).
        # Generic _serde вызывает from_dict(cls, data) а не cls.from_dict —
        # нормализуем name здесь, до вызова generic serde.
        if isinstance(data, dict) and "name" in data:
            raw_name = data["name"]
            if isinstance(raw_name, str):
                data = {**data, "name": {"name": raw_name}}
            elif isinstance(raw_name, dict) and "defaultName" in raw_name:
                # Wire camelCase → snake_case
                normalized = {**raw_name, "default_name": raw_name["defaultName"]}
                normalized.pop("defaultName", None)
                data = {**data, "name": normalized}
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)
