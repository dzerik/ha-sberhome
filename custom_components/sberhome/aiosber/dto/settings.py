"""DTO канала настроек StarOS-устройств (колонок Сбера).

Формат — server-driven UI: сервер отдаёт дерево узлов, каждый со своим `type`
(TOGGLE / SLIDER / RADIO_BUTTONS / EQUALIZER / CARD / SECTION_HEADER / …). Клиент
рендерит что пришло, не зная моделей заранее. Поэтому `SettingNodeDto` намеренно
«широкий» и resilient: все поля optional, неизвестные ключи игнорируются, любой
`type` переживается без падения.

Ключи wire-формата — camelCase (`deviceId`, `serialNumber`, `radioButtons`,
`unitSymbol`, `iconUrl`, `minMaxStep`, `activePreset`), поэтому у DTO кастомный
`from_dict` с ремаппингом на snake_case-поля.

Pure dataclasses, ZERO HA imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Self


@dataclass(slots=True, frozen=True)
class StarosDeviceDto:
    """Устройство StarOS из `POST /v18/devices`."""

    device_id: str | None = None
    serial_number: str | None = None
    product: str | None = None
    name: str | None = None
    icon: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if not isinstance(data, dict):
            return None
        return cls(
            device_id=data.get("deviceId"),
            serial_number=data.get("serialNumber"),
            product=data.get("product"),
            name=data.get("name") or data.get("title"),
            icon=data.get("icon") or data.get("iconUrl"),
        )


@dataclass(slots=True, frozen=True)
class SettingOptionDto:
    """Вариант выбора (radioButtons[] / values[])."""

    title: str | None = None
    value: Any = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if not isinstance(data, dict):
            return None
        return cls(title=data.get("title"), value=data.get("value"))


@dataclass(slots=True, frozen=True)
class SettingNodeDto:
    """Узел server-driven экрана настроек. Все поля optional (resilient)."""

    id: str | None = None
    type: str | None = None
    title: str | None = None
    subtitle: str | None = None

    # Текущие значения по типам (какой заполнен — зависит от type):
    enabled: bool | None = None  # TOGGLE
    checked: str | None = None  # RADIO_BUTTONS (текущий value)
    value: Any = None  # SLIDER / generic

    # Варианты и диапазоны:
    options: list[SettingOptionDto] = field(default_factory=list)  # radioButtons / values
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    unit: str | None = None

    # Навигация / поведение:
    action: str | None = None  # "openScreen" у CARD → рекурсия в подэкран
    disabled: bool | None = None
    icon_url: str | None = None

    # Эквалайзер:
    active_preset: str | None = None
    presets: list[str] = field(default_factory=list)
    frequencies: list[int] = field(default_factory=list)
    min_max_step: list[float] = field(default_factory=list)
    user_bands: list[float] = field(default_factory=list)  # текущие уровни полос

    # Дети: `items` группы, либо раскрытый подэкран CARD (get_settings_deep).
    children: list[SettingNodeDto] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if not isinstance(data, dict):
            return None
        opts_raw = data.get("radioButtons") or data.get("values") or []
        options = [o for o in (SettingOptionDto.from_dict(x) for x in opts_raw) if o]
        items_raw = data.get("items") or []
        children = [c for c in (cls.from_dict(x) for x in items_raw) if c]
        mms = data.get("minMaxStep") or []
        # Текущие уровни полос эквалайзера: userPreset.user, либо value.user.
        up = data.get("userPreset")
        bands_raw = up.get("user") if isinstance(up, dict) else None
        if bands_raw is None and isinstance(data.get("value"), dict):
            bands_raw = data["value"].get("user")
        return cls(
            id=data.get("id"),
            type=data.get("type"),
            title=data.get("title"),
            subtitle=data.get("subtitle"),
            enabled=data.get("enabled"),
            checked=data.get("checked"),
            value=data.get("value"),
            options=options,
            minimum=_num(data.get("min")),
            maximum=_num(data.get("max")),
            step=_num(data.get("step")),
            unit=data.get("unitSymbol") or data.get("unit"),
            action=data.get("action"),
            disabled=data.get("disabled"),
            icon_url=data.get("iconUrl"),
            active_preset=data.get("activePreset"),
            presets=[str(p) for p in (data.get("presets") or [])],
            frequencies=[int(f) for f in (data.get("frequencies") or []) if _is_num(f)],
            min_max_step=[float(x) for x in mms if _is_num(x)],
            user_bands=[float(x) for x in (bands_raw or []) if _is_num(x)],
            children=children,
        )

    @property
    def current_value(self) -> Any:
        """Текущее значение, независимо от типа узла."""
        if self.enabled is not None:
            return self.enabled
        if self.checked is not None:
            return self.checked
        return self.value

    @property
    def opens_screen(self) -> bool:
        """CARD, открывающий подэкран настроек (для рекурсии)."""
        return self.action == "openScreen"


@dataclass(slots=True, frozen=True)
class SettingScreenDto:
    """Экран настроек из `POST /v18/devices/settings`."""

    header: str | None = None
    settings: list[SettingNodeDto] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if not isinstance(data, dict):
            return None
        raw = data.get("settings") or []
        nodes = [n for n in (SettingNodeDto.from_dict(x) for x in raw) if n]
        return cls(header=data.get("header"), settings=nodes)


def _is_num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _num(v: Any) -> float | None:
    return float(v) if _is_num(v) else None


__all__ = [
    "SettingNodeDto",
    "SettingOptionDto",
    "SettingScreenDto",
    "StarosDeviceDto",
]
