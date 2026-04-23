"""Шторы / ворота / клапаны — `curtain`, `window_blind`, `gate`, `valve`."""

from __future__ import annotations

from ._base import TypedDevice


class _OpenCloseMixin:
    """Базовая логика для open/close устройств с прогрессом 0-100.

    Mixin предполагает, что класс наследует от `TypedDevice`,
    предоставляющего `_reported_value(key)`.
    """

    @property
    def position(self: TypedDevice) -> int | None:  # type: ignore[misc]
        """0 (закрыто) — 100 (открыто)."""
        v = self._reported_value("open_percentage")
        return int(v) if v is not None else None

    @property
    def state(self: TypedDevice) -> str | None:  # type: ignore[misc]
        """`open` / `close` / `opening` / `closing`."""
        return self._reported_value("open_state")

    # ----- Config-fields (из APIа CurtainState) -----
    @property
    def reverse_mode(self: TypedDevice) -> bool | None:  # type: ignore[misc]
        """Инверсия направления (open ↔ close меняются местами)."""
        return self._reported_bool("reverse_mode")

    @property
    def opening_time(self: TypedDevice) -> int | None:  # type: ignore[misc]
        """Время полного открытия в секундах (config)."""
        return self._reported_int("opening_time")

    @property
    def calibration(self: TypedDevice) -> str | None:  # type: ignore[misc]
        """Состояние калибровки."""
        return self._reported_str("calibration")

    @property
    def is_open(self) -> bool | None:
        s = self.state
        if s is None:
            return None
        return s in ("open", "opened")

    @property
    def is_opening(self) -> bool | None:
        return self.state == "opening"

    @property
    def is_closing(self) -> bool | None:
        return self.state == "closing"


class CurtainDevice(_OpenCloseMixin, TypedDevice):
    """Шторы. Поддерживает двустворчатые (open_left_*/open_right_*)."""

    CATEGORIES = ("curtain",)

    @property
    def open_rate(self) -> str | None:
        """Скорость открытия: `auto` / `low` / `high`."""
        return self._reported_str("open_rate")

    @property
    def has_left_panel(self) -> bool:
        return self.has_feature("open_left_set")

    @property
    def has_right_panel(self) -> bool:
        return self.has_feature("open_right_set")

    @property
    def left_position(self) -> int | None:
        v = self._reported_value("open_left_percentage")
        return int(v) if v is not None else None

    @property
    def right_position(self) -> int | None:
        v = self._reported_value("open_right_percentage")
        return int(v) if v is not None else None

    @property
    def show_setup(self) -> bool | None:
        """Показывать setup в UI (config из APIа)."""
        return self._reported_bool("show_setup")


class WindowBlindDevice(_OpenCloseMixin, TypedDevice):
    """Жалюзи."""

    CATEGORIES = ("window_blind",)

    @property
    def open_rate(self) -> str | None:
        return self._reported_str("open_rate")

    @property
    def light_transmission(self) -> int | None:
        """Процент пропускания света (для жалюзи) — есть в registry CATEGORY_NUMBERS."""
        return self._reported_int("light_transmission_percentage")


class GateDevice(_OpenCloseMixin, TypedDevice):
    """Ворота. Часто двустворчатые (open_left_/open_right_)."""

    CATEGORIES = ("gate",)

    @property
    def open_rate(self) -> str | None:
        """Скорость открытия: `auto` / `low` / `high`."""
        return self._reported_str("open_rate")

    @property
    def has_left_panel(self) -> bool:
        return self.has_feature("open_left_set")

    @property
    def has_right_panel(self) -> bool:
        return self.has_feature("open_right_set")

    @property
    def left_position(self) -> int | None:
        v = self._reported_value("open_left_percentage")
        return int(v) if v is not None else None

    @property
    def right_position(self) -> int | None:
        v = self._reported_value("open_right_percentage")
        return int(v) if v is not None else None


class ValveDevice(_OpenCloseMixin, TypedDevice):
    """Клапан (вода/газ). Только бинарное состояние, без позиционирования."""

    CATEGORIES = ("valve",)

    @property
    def fault_alarm(self) -> str | None:
        """Состояние тревоги клапана: `alarm` / `external` / `normal` (ValveFaultAlarmAttr)."""
        return self._reported_str("fault_alarm")
