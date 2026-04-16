"""Электрика — `socket` и `relay`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._base import TypedDevice

if TYPE_CHECKING:
    pass


class _PowerMonitorMixin:
    """Mixin для устройств с измерением напряжения/тока/мощности.

    Sber wire единицы:
    - voltage — вольты (V)
    - current — миллиамперы (mA), HA принято делить на 1000 → амперы.
    - power — ватты (W). Range 10-45000.

    Mixin предполагает, что класс наследует от `TypedDevice`,
    предоставляющего `_reported_int(key)`.
    """

    @property
    def voltage(self: TypedDevice):  # type: ignore[misc]
        # Sber API даёт voltage / current / power. На некоторых устройствах
        # с префиксом `cur_` (cur_voltage, cur_current, cur_power).
        return self._reported_int("voltage") or self._reported_int("cur_voltage")

    @property
    def current_milliamps(self: TypedDevice):  # type: ignore[misc]
        return self._reported_int("current") or self._reported_int("cur_current")

    @property
    def current_amps(self) -> float | None:
        ma = self.current_milliamps
        return ma / 1000.0 if ma is not None else None

    @property
    def power_watts(self: TypedDevice) -> int | None:  # type: ignore[misc]
        return self._reported_int("power") or self._reported_int("cur_power")


class SocketDevice(_PowerMonitorMixin, TypedDevice):
    """Умная розетка с измерением + child_lock."""

    CATEGORIES = ("socket",)

    @property
    def is_on(self) -> bool | None:
        return self._reported_bool("on_off")

    @property
    def child_lock(self) -> bool | None:
        return self._reported_bool("child_lock")

    @property
    def upper_current_threshold(self) -> int | None:
        """Защитный порог тока (mA), config-значение."""
        return self._reported_int("upper_current_threshold")


class RelayDevice(_PowerMonitorMixin, TypedDevice):
    """Реле (без child_lock)."""

    CATEGORIES = ("relay",)

    @property
    def is_on(self) -> bool | None:
        return self._reported_bool("on_off")
