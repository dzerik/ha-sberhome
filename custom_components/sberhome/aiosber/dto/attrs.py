"""AttrKey constants — все известные ключи AttributeValueDto.key.

Список ключей составлен на основе наблюдения трафика REST/WS Sber
Gateway API и дополняется по мере появления новых атрибутов.

Использование:

    from custom_components.sberhome.aiosber.dto import (
        AttrKey, AttributeValueDto, AttributeValueType,
    )

    cmd = AttributeValueDto(
        key=AttrKey.ON_OFF,
        type=AttributeValueType.BOOL,
        bool_value=True,
    )
"""

from __future__ import annotations

from typing import Final


class AttrKey:
    """Namespace со строковыми константами ключей атрибутов.

    Не enum — потому что значения ключей могут быть произвольными строками
    (например `button_3_event` динамически), enum закрыл бы это.
    """

    # ---- on/off + общие ----
    ON_OFF: Final = "on_off"
    ONLINE: Final = "online"
    CHILD_LOCK: Final = "child_lock"
    SLEEP_TIMER: Final = "sleep_timer"
    POWER_ON_MODE: Final = "power_on_mode"

    # ---- электрика ----
    CUR_VOLTAGE: Final = "cur_voltage"
    CUR_CURRENT: Final = "cur_current"
    CUR_POWER: Final = "cur_power"
    VOLTAGE: Final = "voltage"
    CURRENT: Final = "current"
    POWER: Final = "power"
    UPPER_CURRENT_THRESHOLD: Final = "upper_current_threshold"

    # ---- свет ----
    LIGHT_BRIGHTNESS: Final = "light_brightness"
    LIGHT_COLOUR: Final = "light_colour"
    LIGHT_COLOUR_TEMP: Final = "light_colour_temp"
    LIGHT_MODE: Final = "light_mode"
    LIGHT_SCENE: Final = "light_scene"
    LIGHTING_TYPE: Final = "lighting_type"
    MAX_BRIGHTNESS_DAWN: Final = "max_brightness_dawn"
    MAX_BRIGHTNESS_SUNSET: Final = "max_brightness_sunset"
    DURATION_DAWN: Final = "duration_dawn"
    DURATION_SUNSET: Final = "duration_sunset"

    # ---- климат-датчик ----
    TEMPERATURE: Final = "temperature"
    HUMIDITY: Final = "humidity"
    AIR_PRESSURE: Final = "air_pressure"
    TEMP_UNIT_VIEW: Final = "temp_unit_view"
    TEMP_UNIT_CONVERT: Final = "temp_unit_convert"
    SENSOR_SENSITIVE: Final = "sensor_sensitive"

    # ---- бинарные датчики ----
    DOORCONTACT_STATE: Final = "doorcontact_state"
    PIR: Final = "pir"
    MOTION_STATE: Final = "motion_state"
    WATER_LEAK_STATE: Final = "water_leak_state"
    SMOKE_STATE: Final = "smoke_state"
    GAS_LEAK_STATE: Final = "gas_leak_state"
    TAMPER_ALARM: Final = "tamper_alarm"
    ALARM_MUTE: Final = "alarm_mute"
    # notification toggles — Sber шлёт флаги "отправлять ли SMS/push
    # при сработке датчика".  Названия — канал уведомления + тип датчика.
    SMS_PIR: Final = "sms_pir"
    PUSH_PIR: Final = "push_pir"
    SMS_WATER_LEAK_STATE: Final = "sms_water_leak_state"
    PUSH_WATER_LEAK_STATE: Final = "push_water_leak_state"

    # ---- общие диагностика ----
    BATTERY_PERCENTAGE: Final = "battery_percentage"
    BATTERY_LOW_POWER: Final = "battery_low_power"
    SIGNAL_STRENGTH: Final = "signal_strength"
    SIGNAL_STRENGTH_DBM: Final = "signal_strength_dbm"

    # ---- cover (шторы/ворота/клапаны) ----
    OPEN_PERCENTAGE: Final = "open_percentage"
    OPEN_SET: Final = "open_set"
    OPEN_STATE: Final = "open_state"
    OPEN_RATE: Final = "open_rate"
    OPEN_LEFT_PERCENTAGE: Final = "open_left_percentage"
    OPEN_LEFT_SET: Final = "open_left_set"
    OPEN_LEFT_STATE: Final = "open_left_state"
    OPEN_RIGHT_PERCENTAGE: Final = "open_right_percentage"
    OPEN_RIGHT_SET: Final = "open_right_set"
    OPEN_RIGHT_STATE: Final = "open_right_state"
    REVERSE_MODE: Final = "reverse_mode"
    OPENING_TIME: Final = "opening_time"
    CALIBRATION: Final = "calibration"
    SHOW_SETUP: Final = "show_setup"

    # ---- HVAC ----
    HVAC_TEMP_SET: Final = "hvac_temp_set"
    HVAC_HUMIDITY: Final = "hvac_humidity"
    HVAC_WORK_MODE: Final = "hvac_work_mode"
    HVAC_AIR_FLOW_POWER: Final = "hvac_air_flow_power"
    HVAC_AIR_FLOW_DIRECTION: Final = "hvac_air_flow_direction"
    HVAC_HUMIDITY_SET: Final = "hvac_humidity_set"
    HVAC_NIGHT_MODE: Final = "hvac_night_mode"
    HVAC_IONIZATION: Final = "hvac_ionization"
    HVAC_AROMATIZATION: Final = "hvac_aromatization"
    HVAC_DECONTAMINATE: Final = "hvac_decontaminate"
    HVAC_REPLACE_FILTER: Final = "hvac_replace_filter"
    HVAC_REPLACE_IONIZATOR: Final = "hvac_replace_ionizator"
    HVAC_THERMOSTAT_MODE: Final = "hvac_thermostat_mode"
    HVAC_HEATING_RATE: Final = "hvac_heating_rate"
    HVAC_WATER_LEVEL: Final = "hvac_water_level"
    HVAC_WATER_PERCENTAGE: Final = "hvac_water_percentage"
    HVAC_WATER_LOW_LEVEL: Final = "hvac_water_low_level"
    HVAC_HYSTERESIS: Final = "heating_hysteresis"
    HVAC_ANTI_FROST_TEMP: Final = "anti_frost_temp"
    HVAC_OPEN_WINDOW: Final = "open_window"
    HVAC_OPEN_WINDOW_STATUS: Final = "open_window_status"
    HVAC_FLOOR_TYPE: Final = "floor_type"
    HVAC_FLOOR_SENSOR_TYPE: Final = "floor_sensor_type"
    HVAC_MAIN_SENSOR: Final = "main_sensor"
    HVAC_DEVICE_CONDITION: Final = "device_condition"
    HVAC_TEMPERATURE_CORRECTION: Final = "temperature_correction"
    HVAC_MIN_TEMPERATURE: Final = "min_temperature"
    HVAC_MAX_TEMPERATURE: Final = "max_temperature"
    HVAC_ADJUST_FLOOR_TEMP: Final = "adjust_floor_temp"

    # ---- кухня (чайник) ----
    KITCHEN_WATER_TEMPERATURE: Final = "kitchen_water_temperature"
    KITCHEN_WATER_TEMPERATURE_SET: Final = "kitchen_water_temperature_set"
    KITCHEN_WATER_LEVEL: Final = "kitchen_water_level"
    KITCHEN_WATER_LOW_LEVEL: Final = "kitchen_water_low_level"

    # ---- пылесос ----
    VACUUM_CLEANER_COMMAND: Final = "vacuum_cleaner_command"
    VACUUM_CLEANER_STATUS: Final = "vacuum_cleaner_status"
    VACUUM_CLEANER_PROGRAM: Final = "vacuum_cleaner_program"
    VACUUM_CLEANER_CLEANING_TYPE: Final = "vacuum_cleaner_cleaning_type"

    # ---- TV / media ----
    SOURCE: Final = "source"
    VOLUME: Final = "volume"
    VOLUME_INT: Final = "volume_int"
    CHANNEL: Final = "channel"
    CHANNEL_INT: Final = "channel_int"
    NUMBER: Final = "number"
    MUTE: Final = "mute"
    CUSTOM_KEY: Final = "custom_key"
    DIRECTION: Final = "direction"

    # ---- сценарные кнопки ----
    DIRECTIONAL_CLICK: Final = "directional_click"
    BUTTON_EVENT: Final = "button_event"

    # button_N_event — динамические, см. button_event_key()

    # ---- пользовательский список (стоп-лист / избранное) ----
    BD_LIST_TEXT_1: Final = "bd_list_text_1"

    # ---- домофон ----
    INCOMING_CALL: Final = "incoming_call"
    REJECT_CALL: Final = "reject_call"
    UNLOCK: Final = "unlock"
    INTERCOM_MUTE: Final = "intercom_mute"
    UNLOCK_DURATION: Final = "unlock_duration"
    VIRTUAL_OPEN_STATE: Final = "virtual_open_state"

    # ---- индикация LED у scenario_button ----
    LED_INDICATOR_ON: Final = "led_indicator_on"
    LED_INDICATOR_OFF: Final = "led_indicator_off"
    COLOR_INDICATOR_ON: Final = "color_indicator_on"
    COLOR_INDICATOR_OFF: Final = "color_indicator_off"
    CLICK_MODE: Final = "click_mode"
    IS_DOUBLE_CLICK_ENABLED: Final = "is_double_click_enabled"

    # ---- камеры ----
    NIGHTVISION: Final = "nightvision"
    RECORD_MODE: Final = "record_mode"
    SD_STATUS: Final = "sd_status"
    SD_FORMAT_STATUS: Final = "sd_format_status"
    DECIBEL_SENSITIVITY: Final = "decibel_sensitivity"
    MOTION_SENSITIVITY: Final = "motion_sensitivity"
    ANTIFLICKER: Final = "antiflicker"

    # ---- valve ----
    FAULT_ALARM: Final = "fault_alarm"

    # ---- расписание ----
    SCHEDULE: Final = "schedule"
    SCHEDULE_STATUS: Final = "schedule_status"


def button_event_key(n: int) -> str:
    """Динамический ключ события сценарной кнопки: button_1_event ... button_10_event."""
    if not 1 <= n <= 10:
        raise ValueError(f"button index out of range: {n}")
    return f"button_{n}_event"
