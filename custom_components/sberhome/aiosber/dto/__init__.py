"""DTO-слой для Sber Smart Home Gateway API.

Полная типизированная модель API/WS, основанная на wire-анализе
Sber wire-протокол.

Базовое использование:

    from custom_components.sberhome.aiosber.dto import (
        DeviceDto,
        DesiredDeviceStateDto,
        AttributeValueDto,
        AttrKey,
        AttributeValueType,
        ColorValue,
        WorkModeAttr,
    )

    # Парсинг ответа GET /devices/
    devices = [DeviceDto.from_dict(d) for d in response_json["result"]]

    # Отправка команды
    body = DesiredDeviceStateDto(desired_state=[
        AttributeValueDto.of_bool(AttrKey.ON_OFF, True),
        AttributeValueDto.of_color(
            AttrKey.LIGHT_COLOUR,
            ColorValue(hue=120, saturation=100, brightness=80),
        ),
    ])
    await client.put(f"devices/{device_id}/state", json=body.to_dict())
"""

from __future__ import annotations

from .attrs import AttrKey, button_event_key
from .body import (
    ChangeDeviceOrderElementsBody,
    CreateDeviceLinkBody,
    DeviceToPairingBody,
    IndicatorColorBody,
    UpdateNameBody,
    UpdateParentBody,
)
from .category import DeviceCategoryDto
from .device import (
    BridgeMeta,
    ChildrenDto,
    CommandDto,
    DeviceCorrectionDto,
    DeviceDto,
    DeviceInfoDto,
    DeviceLinkDto,
    ImagesDto,
    IndicatorColor,
    IndicatorColors,
    NameDto,
    OwnerInfoDto,
)
from .devman import DevmanDto
from .enums import (
    AntiflickerAttr,
    AttributeValueType,
    ButtonEvent,
    CategoryOverrideAttr,
    ChannelAttr,
    ConnectionType,
    CustomKeyAttr,
    DecibelSensitivityAttr,
    DeviceConditionAttr,
    DeviceImageSize,
    DeviceLinkType,
    DirectionAttr,
    ElementType,
    FloorSensorTypeAttr,
    FloorTypeAttr,
    HvacAirFlowPower,
    HvacHeatingRateAttr,
    HvacSystemModeAttr,
    HvacThermostatModeAttr,
    HvacWorkMode,
    LightingTypeAttr,
    LightOperationModeAttr,
    MainSensorAttr,
    MotionSensitivityAttr,
    NightvisionAttr,
    OpenSetAttr,
    OpenStateAttr,
    PositionAttr,
    PowerModeAttr,
    RecordModeAttr,
    ScheduleDay,
    ScheduleStatusAttr,
    SdFormatStatusAttr,
    SdStatusAttr,
    SensorLevelAttr,
    SensorSensitiveAttr,
    SignalStrengthAttr,
    SourceAttr,
    TemperatureUnitAttr,
    Topic,
    VacuumCommand,
    VacuumProgram,
    ValveAlarmStateAttr,
    ValveFaultAlarmAttr,
    VendorType,
    VolumeAttr,
    WaterLeakSensorModeAttr,
    WorkModeAttr,
)
from .feature import (
    ColorRange,
    ColorValues,
    DeviceFeatureDto,
    EnumValues,
    FloatRange,
    FloatValues,
    IntRange,
    IntValues,
    StringValues,
)
from .group import GroupStateDto
from .home import HomeChangeVariableDto
from .ota import OtaUpdateInfoDto
from .scenario import ScenarioDto, ScenarioWidgetDto
from .state import (
    DesiredDeviceStateDto,
    DesiredGroupStateDto,
    DeviceOrderElement,
    StateDto,
)
from .transfer import HomeTransferBaseDto
from .union import UnionDto, UnionTreeDto, UnionType
from .values import (
    AttributeValueDto,
    ColorValue,
    ScheduleEvent,
    ScheduleValue,
)
from .ws import SocketMessageDto

__all__ = [
    # attrs
    "AttrKey",
    "button_event_key",
    # values
    "AttributeValueDto",
    "ColorValue",
    "ScheduleEvent",
    "ScheduleValue",
    # category
    "DeviceCategoryDto",
    # devman
    "DevmanDto",
    # device
    "BridgeMeta",
    "ChildrenDto",
    "CommandDto",
    "DeviceCorrectionDto",
    "DeviceDto",
    "DeviceInfoDto",
    "DeviceLinkDto",
    "ImagesDto",
    "NameDto",
    "IndicatorColor",
    "IndicatorColors",
    "OwnerInfoDto",
    # feature
    "ColorRange",
    "ColorValues",
    "DeviceFeatureDto",
    "EnumValues",
    "FloatRange",
    "FloatValues",
    "IntRange",
    "IntValues",
    "StringValues",
    # group
    "GroupStateDto",
    # home
    "HomeChangeVariableDto",
    # ota
    "OtaUpdateInfoDto",
    # scenario
    "ScenarioDto",
    "ScenarioWidgetDto",
    # transfer
    "HomeTransferBaseDto",
    # union
    "UnionDto",
    "UnionTreeDto",
    "UnionType",
    # state
    "DesiredDeviceStateDto",
    "DesiredGroupStateDto",
    "DeviceOrderElement",
    "StateDto",
    # body
    "ChangeDeviceOrderElementsBody",
    "CreateDeviceLinkBody",
    "DeviceToPairingBody",
    "IndicatorColorBody",
    "UpdateNameBody",
    "UpdateParentBody",
    # ws
    "SocketMessageDto",
    # enums
    "AntiflickerAttr",
    "AttributeValueType",
    "ButtonEvent",
    "CategoryOverrideAttr",
    "ChannelAttr",
    "ConnectionType",
    "CustomKeyAttr",
    "DecibelSensitivityAttr",
    "DeviceConditionAttr",
    "DeviceImageSize",
    "DeviceLinkType",
    "DirectionAttr",
    "ElementType",
    "FloorSensorTypeAttr",
    "FloorTypeAttr",
    "HvacAirFlowPower",
    "HvacHeatingRateAttr",
    "HvacSystemModeAttr",
    "HvacThermostatModeAttr",
    "HvacWorkMode",
    "LightingTypeAttr",
    "LightOperationModeAttr",
    "MainSensorAttr",
    "MotionSensitivityAttr",
    "NightvisionAttr",
    "OpenSetAttr",
    "OpenStateAttr",
    "PositionAttr",
    "PowerModeAttr",
    "RecordModeAttr",
    "ScheduleDay",
    "ScheduleStatusAttr",
    "SdFormatStatusAttr",
    "SdStatusAttr",
    "SensorLevelAttr",
    "SensorSensitiveAttr",
    "SignalStrengthAttr",
    "SourceAttr",
    "TemperatureUnitAttr",
    "Topic",
    "VacuumCommand",
    "VacuumProgram",
    "ValveAlarmStateAttr",
    "ValveFaultAlarmAttr",
    "VendorType",
    "VolumeAttr",
    "WaterLeakSensorModeAttr",
    "WorkModeAttr",
]
