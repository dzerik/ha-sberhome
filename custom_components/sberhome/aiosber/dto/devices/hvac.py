"""HVAC — кондиционеры, обогреватели, радиаторы, бойлеры, тёплый пол, вентиляторы,
очистители воздуха, увлажнители."""

from __future__ import annotations

from ._base import TypedDevice


class _HvacBaseDevice(TypedDevice):
    """Общие поля HVAC: on_off, target temp, current temp."""

    @property
    def is_on(self) -> bool | None:
        return self._reported_bool("on_off")

    @property
    def target_temperature(self) -> int | None:
        return self._reported_int("hvac_temp_set")

    @property
    def current_temperature(self) -> float | None:
        return self._reported_float("temperature")


class _ThermostatMixin:
    """Mixin для устройств с термостатом (Radiator/Boiler/Underfloor).

    Поля термостата — большинство являются config-фичами,
    отображаемыми только при наличии в reported_state.
    """

    @property
    def min_temperature(self: TypedDevice) -> int | None:  # type: ignore[misc]
        """Минимально-допустимая температура (config-граница)."""
        return self._reported_int("min_temperature")

    @property
    def max_temperature(self: TypedDevice) -> int | None:  # type: ignore[misc]
        return self._reported_int("max_temperature")

    @property
    def device_condition(self: TypedDevice) -> str | None:  # type: ignore[misc]
        """`warm` / `emergency_heating` / `off` (DeviceConditionAttr)."""
        return self._reported_str("device_condition")

    @property
    def heating_hysteresis(self: TypedDevice) -> int | None:  # type: ignore[misc]
        """Гистерезис температуры (десятые доли °C)."""
        return self._reported_int("heating_hysteresis")

    @property
    def anti_frost_temp(self: TypedDevice) -> int | None:  # type: ignore[misc]
        """Анти-замерзание (минимальная температура)."""
        return self._reported_int("anti_frost_temp")

    @property
    def temperature_correction(self: TypedDevice) -> int | None:  # type: ignore[misc]
        return self._reported_int("temperature_correction")

    @property
    def schedule_status(self: TypedDevice) -> str | None:  # type: ignore[misc]
        """`active` / `inactive` / `empty` (ScheduleStatusAttr)."""
        return self._reported_str("schedule_status")

    @property
    def open_window(self: TypedDevice) -> bool | None:  # type: ignore[misc]
        """Включена функция «обнаружение открытого окна»."""
        return self._reported_bool("open_window")

    @property
    def open_window_status(self: TypedDevice) -> bool | None:  # type: ignore[misc]
        """Текущее состояние «окно открыто» (если функция активна)."""
        return self._reported_bool("open_window_status")

    @property
    def floor_type(self: TypedDevice) -> str | None:  # type: ignore[misc]
        """Тип пола: `tile`/`wood`/`laminate`/`carpet`/`linoleum`/`quartzvinyl` (FloorTypeAttr)."""
        return self._reported_str("floor_type")

    @property
    def floor_sensor_type(self: TypedDevice) -> str | None:  # type: ignore[misc]
        """Тип датчика пола: NTC10k/NTC4k7/NTC6k8/... (FloorSensorTypeAttr)."""
        return self._reported_str("floor_sensor_type")

    @property
    def main_sensor(self: TypedDevice) -> str | None:  # type: ignore[misc]
        """Какой датчик основной: `C` (корпус) / `CL` (пол) / `B` (выносной) (MainSensorAttr)."""
        return self._reported_str("main_sensor")


class AirConditionerDevice(_HvacBaseDevice):
    """Кондиционер."""

    CATEGORIES = ("hvac_ac",)

    @property
    def work_mode(self) -> str | None:
        """`cool` / `heat` / `dry` / `fan_only` / `auto`."""
        return self._reported_str("hvac_work_mode")

    @property
    def fan_speed(self) -> str | None:
        """`auto` / `low` / `medium` / `high` / `turbo`."""
        return self._reported_str("hvac_air_flow_power")

    @property
    def air_flow_direction(self) -> str | None:
        return self._reported_str("hvac_air_flow_direction")

    @property
    def target_humidity(self) -> int | None:
        return self._reported_int("hvac_humidity_set")

    @property
    def humidity(self) -> int | None:
        """Текущая влажность (если устройство умеет измерять)."""
        return self._reported_int("humidity")

    @property
    def night_mode(self) -> bool | None:
        return self._reported_bool("hvac_night_mode")

    @property
    def ionization(self) -> bool | None:
        return self._reported_bool("hvac_ionization")


class HeaterDevice(_HvacBaseDevice):
    """Обогреватель."""

    CATEGORIES = ("hvac_heater",)

    @property
    def thermostat_mode(self) -> str | None:
        """`eco` / `comfort` / `boost` / `auto` / `heating`."""
        return self._reported_str("hvac_thermostat_mode")

    @property
    def fan_speed(self) -> str | None:
        return self._reported_str("hvac_air_flow_power")


class RadiatorDevice(_ThermostatMixin, _HvacBaseDevice):
    """Радиатор отопления (target 25-40 °C step 5).

    Наследует ThermostatMixin — поддерживает min/max/condition/hysteresis/
    anti_frost/correction/schedule/open_window/floor_type/sensor/main_sensor.
    Все поля — config, отображаются только при наличии в reported_state.
    """

    CATEGORIES = ("hvac_radiator",)

    @property
    def child_lock(self) -> bool | None:
        return self._reported_bool("child_lock")

    @property
    def adjust_floor_temp(self) -> bool | None:
        return self._reported_bool("adjust_floor_temp")

    @property
    def show_setup(self) -> bool | None:
        return self._reported_bool("show_setup")


class BoilerDevice(_ThermostatMixin, _HvacBaseDevice):
    """Бойлер (target 25-80 °C step 5)."""

    CATEGORIES = ("hvac_boiler",)

    @property
    def thermostat_mode(self) -> str | None:
        return self._reported_str("hvac_thermostat_mode")

    @property
    def heating_rate(self) -> str | None:
        """`auto` / `low` / `medium` / `high`."""
        return self._reported_str("hvac_heating_rate")

    @property
    def schedule(self):
        """Расписание включений (ScheduleValue с днями недели и event'ами)."""
        attr = self._dto.reported("schedule")
        return attr.schedule_value if attr else None


class UnderfloorHeatingDevice(_ThermostatMixin, _HvacBaseDevice):
    """Тёплый пол (target 25-50 °C step 5)."""

    CATEGORIES = ("hvac_underfloor_heating",)

    @property
    def thermostat_mode(self) -> str | None:
        return self._reported_str("hvac_thermostat_mode")


class FanDevice(_HvacBaseDevice):
    """Вентилятор."""

    CATEGORIES = ("hvac_fan",)

    @property
    def speed(self) -> str | None:
        return self._reported_str("hvac_air_flow_power")


class AirPurifierDevice(_HvacBaseDevice):
    """Очиститель воздуха."""

    CATEGORIES = ("hvac_air_purifier",)

    @property
    def speed(self) -> str | None:
        return self._reported_str("hvac_air_flow_power")

    @property
    def night_mode(self) -> bool | None:
        return self._reported_bool("hvac_night_mode")

    @property
    def ionization(self) -> bool | None:
        return self._reported_bool("hvac_ionization")

    @property
    def aromatization(self) -> bool | None:
        return self._reported_bool("hvac_aromatization")

    @property
    def decontaminate(self) -> bool | None:
        """UV/обеззараживание (есть на топовых моделях)."""
        return self._reported_bool("hvac_decontaminate")

    @property
    def replace_filter_alarm(self) -> bool | None:
        return self._reported_bool("hvac_replace_filter")

    @property
    def replace_ionizer_alarm(self) -> bool | None:
        return self._reported_bool("hvac_replace_ionizator")


class HumidifierDevice(_HvacBaseDevice):
    """Увлажнитель воздуха."""

    CATEGORIES = ("hvac_humidifier",)

    @property
    def humidity(self) -> int | None:
        """Текущая влажность."""
        return self._reported_int("humidity")

    @property
    def target_humidity(self) -> int | None:
        return self._reported_int("hvac_humidity_set")

    @property
    def speed(self) -> str | None:
        return self._reported_str("hvac_air_flow_power")

    @property
    def night_mode(self) -> bool | None:
        return self._reported_bool("hvac_night_mode")

    @property
    def ionization(self) -> bool | None:
        return self._reported_bool("hvac_ionization")

    @property
    def water_level(self) -> int | None:
        return self._reported_int("hvac_water_level")

    @property
    def water_percentage(self) -> int | None:
        """Уровень воды как процент (отдельная feature, иногда вместо water_level)."""
        return self._reported_int("hvac_water_percentage")

    @property
    def water_low_alarm(self) -> bool | None:
        return self._reported_bool("hvac_water_low_level")

    @property
    def replace_filter_alarm(self) -> bool | None:
        return self._reported_bool("hvac_replace_filter")

    @property
    def replace_ionizer_alarm(self) -> bool | None:
        return self._reported_bool("hvac_replace_ionizator")
