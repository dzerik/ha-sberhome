"""Бытовая техника — чайник, пылесос, TV."""

from __future__ import annotations

from ._base import TypedDevice


class KettleDevice(TypedDevice):
    """Умный чайник."""

    CATEGORIES = ("kettle",)

    @property
    def is_on(self) -> bool | None:
        return self._reported_bool("on_off")

    @property
    def water_temperature(self) -> float | None:
        """Текущая температура воды."""
        return self._reported_float("kitchen_water_temperature")

    @property
    def target_water_temperature(self) -> int | None:
        """Заданная температура (60-100 °C step 10)."""
        return self._reported_int("kitchen_water_temperature_set")

    @property
    def water_level(self) -> int | None:
        """Уровень воды (%)."""
        return self._reported_int("kitchen_water_level")

    @property
    def water_low_alarm(self) -> bool | None:
        return self._reported_bool("kitchen_water_low_level")

    @property
    def child_lock(self) -> bool | None:
        return self._reported_bool("child_lock")


class VacuumDevice(TypedDevice):
    """Робот-пылесос."""

    CATEGORIES = ("vacuum_cleaner",)

    @property
    def status(self) -> str | None:
        """Текущее состояние пылесоса (working/charging/return_to_base/...)."""
        return self._reported_str("vacuum_cleaner_status")

    @property
    def program(self) -> str | None:
        """`perimeter` / `spot` / `smart`."""
        return self._reported_str("vacuum_cleaner_program")

    @property
    def cleaning_type(self) -> str | None:
        return self._reported_str("vacuum_cleaner_cleaning_type")

    @property
    def child_lock(self) -> bool | None:
        return self._reported_bool("child_lock")


class TvDevice(TypedDevice):
    """Телевизор."""

    CATEGORIES = ("tv",)

    @property
    def is_on(self) -> bool | None:
        return self._reported_bool("on_off")

    @property
    def source(self) -> str | None:
        """Текущий вход (`hdmi1` / `tv` / `av` / `content` / `screencast`)."""
        return self._reported_str("source")

    @property
    def volume(self) -> int | None:
        """0..100 (volume_int)."""
        return self._reported_int("volume_int")

    @property
    def muted(self) -> bool | None:
        return self._reported_bool("mute")

    @property
    def channel(self) -> int | None:
        return self._reported_int("channel_int")
