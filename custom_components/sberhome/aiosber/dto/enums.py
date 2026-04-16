"""All Sber Smart Home enums.

Источник: wire-анализ `com.salute.smarthome.prod`,
пакеты `ru.sberdevices.smarthome.device.models.attributes`
и `ru.sberdevices.smarthome.device.models.fields`.

Каждый enum хранит wire-значение (то, что уходит/приходит в JSON
как `enum_value`) в `.value`. Конструктор `MyEnum(wire_str)` парсит wire.

ВАЖНО: некоторые "очевидные" boolean-like enum'ы (Antiflicker, MotionSensitivity,
Nightvision, DecibelSensitivity) используют **строки с цифрами** "0"/"1"/"2",
не Boolean и не int. SdStatusAttr — единственный INTEGER-wire enum.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


# =============================================================================
# Тип значения AttributeValue
# =============================================================================
class AttributeValueType(StrEnum):
    STRING = "STRING"
    INTEGER = "INTEGER"
    FLOAT = "FLOAT"
    BOOL = "BOOL"
    ENUM = "ENUM"
    JSON = "JSON"
    COLOR = "COLOR"
    SCHEDULE = "SCHEDULE"


# =============================================================================
# *Attr enums (47 штук)
# =============================================================================
class AntiflickerAttr(StrEnum):
    DISABLE = "0"
    HZ_50 = "1"
    HZ_60 = "2"


class CategoryOverrideAttr(StrEnum):
    CURTAINS = "curtain"
    WINDOW_BLIND = "window_blind"
    GATES = "gate"
    LIGHT = "light"
    HVAC_AC = "hvac_ac"
    HVAC_AIR_PURIFIER = "hvac_air_purifier"
    HVAC_BOILER = "hvac_boiler"
    HVAC_FAN = "hvac_fan"
    HVAC_HEATER = "hvac_heater"
    HVAC_UNDERFLOOR_HEATING = "hvac_underfloor_heating"
    HVAC_HUMIDIFIER = "hvac_humidifier"
    KETTLE = "kettle"
    TV = "tv"
    SOCKET = "socket"
    RELAY = "relay"
    SWITCH = "switch"
    UNKNOWN = "unknown"


class ChannelAttr(StrEnum):
    PLUS = "+"
    MINUS = "-"


class CustomKeyAttr(StrEnum):
    CONFIRM = "confirm"
    BACK = "back"
    HOME = "home"


class DecibelSensitivityAttr(StrEnum):
    LOW = "0"
    HIGH = "1"


class DeviceConditionAttr(StrEnum):
    WARM = "warm"
    EMERGENCY_HEATING = "emergency_heating"
    OFF = "off"


class DirectionAttr(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class FloorSensorTypeAttr(StrEnum):
    NTC10K = "NTC10k"
    NTC4K7 = "NTC4k7"
    NTC6K8 = "NTC6k8"
    NTC12K = "NTC12k"
    NTC15K = "NTC15k"
    NTC33K = "NTC33k"
    NTC47K = "NTC47k"


class FloorTypeAttr(StrEnum):
    TILE = "tile"
    WOOD = "wood"
    LAMINATE = "laminate"
    CARPET = "carpet"
    LINOLEUM = "linoleum"
    QUARTZVINYL = "quartzvinyl"


class HvacHeatingRateAttr(StrEnum):
    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HvacSystemModeAttr(StrEnum):
    ON = "on"
    OFF = "off"
    NORMAL = "normal"


class HvacThermostatModeAttr(StrEnum):
    AUTO = "auto"
    HEATING = "heating"
    ECO = "eco"
    FAST_HEATING = "fast_heating"
    TURBO = "turbo"


class LightOperationModeAttr(StrEnum):
    """Wire-значения не восстановлены из wire-протокола; используем имена в нижнем регистре."""

    ANTI_FLICKER = "anti_flicker"
    FAST_REACTION = "fast_reaction"
    FAST_REACTION_WITH_INDICATOR = "fast_reaction_with_indicator"


class LightingTypeAttr(StrEnum):
    MAIN = "main"
    DUTY = "duty"


class MainSensorAttr(StrEnum):
    """Какой датчик температуры основной — корпус (C) / пол (CL) / выносной (B)."""

    C = "C"
    CL = "CL"
    B = "B"


class MotionSensitivityAttr(StrEnum):
    LOW = "0"
    MEDIUM = "1"
    HIGH = "2"


class NightvisionAttr(StrEnum):
    AUTO = "0"
    OFF = "1"
    ON = "2"


class OpenSetAttr(StrEnum):
    """Команда шторам/воротам.

    NB: на некоторых устройствах open_set приходит как INTEGER (target %),
    парсить тип нужно динамически из AttributeValueDto.type.
    """

    OPEN = "open"
    CLOSE = "close"
    FORCE_OPEN = "force_open"
    STOP = "stop"
    UNKNOWN = "unknown"


class OpenStateAttr(StrEnum):
    OPEN = "open"
    CLOSE = "close"
    OPENING = "opening"
    CLOSING = "closing"


class PositionAttr(StrEnum):
    LEFT = "left"
    RIGHT = "right"
    NONE = "none"


class PowerModeAttr(StrEnum):
    ON = "on"
    PREVIOUS = "previous"
    OFF = "off"
    UNKNOWN = "unknown"


class RecordModeAttr(StrEnum):
    MOTION = "1"
    CONTINUOUS = "2"


class ScheduleStatusAttr(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    EMPTY = "empty"


class SdFormatStatusAttr(StrEnum):
    """Wire-значения не восстановлены из wire-протокола; имена в нижнем регистре."""

    FORMATTING = "formatting"
    EXCEPTION = "exception"
    NO_CARD = "no_card"
    ERROR = "error"


class SdStatusAttr(IntEnum):
    """ЕДИНСТВЕННЫЙ INTEGER-wire enum."""

    NORMAL = 1
    EXCEPTION = 2
    NO_SPACE = 3
    FORMATTING = 4
    NO_CARD = 5


class SensorLevelAttr(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SensorSensitiveAttr(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SignalStrengthAttr(StrEnum):
    """Enum-вариант. На большинстве устройств signal_strength — INTEGER (dBm)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceAttr(StrEnum):
    HDMI_1 = "hdmi1"
    HDMI_2 = "hdmi2"
    HDMI_3 = "hdmi3"
    TV = "tv"
    AV = "av"
    CONTENT = "content"
    SCREEN_CAST = "screencast"


class TemperatureUnitAttr(StrEnum):
    CELSIUS = "c"
    FAHRENHEIT = "f"


class ValveAlarmStateAttr(StrEnum):
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


class ValveFaultAlarmAttr(StrEnum):
    ALARM = "alarm"
    EXTERNAL = "external"
    NORMAL = "normal"


class VolumeAttr(StrEnum):
    PLUS = "+"
    MINUS = "-"


class WaterLeakSensorModeAttr(StrEnum):
    NORMAL = "normal"
    IGNORE = "ignore"


class WorkModeAttr(StrEnum):
    """Режим работы лампы (light_mode)."""

    WHITE = "white"
    ADAPTIVE = "adaptive"
    COLOR = "colour"
    SCENE = "scene"
    MUSIC = "music"


# =============================================================================
# fields/ — type/category/connection enums
# =============================================================================
class ConnectionType(StrEnum):
    MATTER = "ConnTypeMatter"
    WIRED = "ConnTypeWired"
    WIRELESS = "ConnTypeWireless"
    ZIGBEE = "ConnTypeZigbee"


class VendorType(StrEnum):
    SBER = "sber"
    SBERDEVICES = "sberdevices"
    TUYA = "tuya"
    TUYA_CN = "tuyacn"
    C2C = "c2c"
    B2B = "b2b"


class DeviceLinkType(StrEnum):
    TEMPERATURE_CORRECTION = "TEMPERATURE_CORRECTION"
    FLOOR_EXT_SENSOR = "FLOOR_EXT_SENSOR"


class DeviceImageSize(StrEnum):
    S = "_s"
    M = "_m"
    L = "_l"
    LW = "_lw"
    XL = "_xl"


# =============================================================================
# Domain HVAC modes (используется в spec, не в wire-протоколе как Attr)
# =============================================================================
class HvacWorkMode(StrEnum):
    COOL = "cool"
    HEAT = "heat"
    DRY = "dry"
    FAN = "fan"
    AUTO = "auto"


class HvacAirFlowPower(StrEnum):
    AUTO = "auto"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    TURBO = "turbo"


# =============================================================================
# Vacuum
# =============================================================================
class VacuumCommand(StrEnum):
    START = "start"
    PAUSE = "pause"
    RETURN_TO_BASE = "return_to_base"
    LOCATE = "locate"


class VacuumProgram(StrEnum):
    PERIMETER = "perimeter"
    SPOT = "spot"
    SMART = "smart"


# =============================================================================
# Scenario button event
# =============================================================================
class ButtonEvent(StrEnum):
    CLICK = "click"
    DOUBLE_CLICK = "double_click"


# =============================================================================
# WS topic
# =============================================================================
class Topic(StrEnum):
    """Топики WebSocket (`wss://ws.iot.sberdevices.ru`).

    Имена snake_case подобраны как соответствующие поля SocketMessageDto.
    Сами строки — рабочие гипотезы; реальный сервер определяет тип по
    тому, какое поле non-null в сообщении (см. dto.ws.SocketMessageDto).
    """

    DEVICE_STATE = "device_state"
    LAUNCHER_WIDGETS = "launcher_widgets"
    SCENARIO_WIDGETS = "scenario_widgets"
    SCENARIO_HOME_CHANGE_VARIABLE = "scenario_home_change_variable"
    INVENTORY_OTA = "inventory_ota"
    DEVMAN_EVENT = "devman_event"
    GROUP_STATE = "group_state"
    HOME_TRANSFER = "home_transfer"


# =============================================================================
# ElementType (для device order)
# =============================================================================
class ElementType(StrEnum):
    DEVICE = "DEVICE"
    GROUP = "GROUP"


# =============================================================================
# Schedule.Day (день недели для ScheduleValue.days)
# =============================================================================
class ScheduleDay(StrEnum):
    """Wire-значения предположены lowercase (источник хранит const-имена)."""

    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"
