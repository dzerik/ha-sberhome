"""Датчики — temp, water_leak, door, pir, smoke, gas."""

from __future__ import annotations

from ._base import TypedDevice


class TemperatureSensorDevice(TypedDevice):
    """Климат-датчик: температура + влажность + давление."""

    CATEGORIES = ("sensor_temp",)

    @property
    def temperature(self) -> float | None:
        """Текущая температура (°C)."""
        return self._reported_float("temperature")

    @property
    def humidity(self) -> int | None:
        """Влажность (%)."""
        return self._reported_int("humidity")

    @property
    def air_pressure(self) -> int | None:
        """Атмосферное давление (hPa)."""
        return self._reported_int("air_pressure")

    @property
    def temp_unit(self) -> str | None:
        """`c` (celsius) / `f` (fahrenheit)."""
        return self._reported_str("temp_unit_view")

    @property
    def sensitivity(self) -> str | None:
        """`auto` / `high`."""
        return self._reported_str("sensor_sensitive")


class WaterLeakSensorDevice(TypedDevice):
    CATEGORIES = ("sensor_water_leak",)

    @property
    def water_leak(self) -> bool | None:
        return self._reported_bool("water_leak_state")


class DoorSensorDevice(TypedDevice):
    """Датчик открытия двери/окна."""

    CATEGORIES = ("sensor_door",)

    @property
    def is_open(self) -> bool | None:
        """True = открыто, False = закрыто."""
        return self._reported_bool("doorcontact_state")

    @property
    def tamper_alarm(self) -> bool | None:
        """Кто-то пытался снять датчик."""
        return self._reported_bool("tamper_alarm")

    @property
    def sensitivity(self) -> str | None:
        return self._reported_str("sensor_sensitive")


class MotionSensorDevice(TypedDevice):
    """PIR — датчик движения."""

    CATEGORIES = ("sensor_pir",)

    @property
    def motion(self) -> bool | None:
        # Spec обязательное поле — `pir`, но многие устройства шлют `motion_state`.
        v = self._reported_bool("pir")
        if v is not None:
            return v
        return self._reported_bool("motion_state")

    @property
    def sensitivity(self) -> str | None:
        return self._reported_str("sensor_sensitive")


class SmokeSensorDevice(TypedDevice):
    CATEGORIES = ("sensor_smoke",)

    @property
    def smoke(self) -> bool | None:
        return self._reported_bool("smoke_state")

    @property
    def alarm_muted(self) -> bool | None:
        return self._reported_bool("alarm_mute")


class GasSensorDevice(TypedDevice):
    CATEGORIES = ("sensor_gas",)

    @property
    def gas_leak(self) -> bool | None:
        return self._reported_bool("gas_leak_state")

    @property
    def alarm_muted(self) -> bool | None:
        return self._reported_bool("alarm_mute")

    @property
    def sensitivity(self) -> str | None:
        return self._reported_str("sensor_sensitive")
