"""DTO-слой для Sber Smart Home Gateway API.

Полная типизированная модель API/WS, основанная на реверс-инжиниринге
APK `com.salute.smarthome.prod` v26.03.1.18015.

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
from .device import (
    BridgeMeta,
    CommandDto,
    DeviceDto,
    DeviceInfoDto,
    ImagesDto,
    IndicatorColor,
    IndicatorColors,
)
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
from .state import (
    DesiredDeviceStateDto,
    DesiredGroupStateDto,
    DeviceOrderElement,
    StateDto,
)
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
    # device
    "BridgeMeta",
    "CommandDto",
    "DeviceDto",
    "DeviceInfoDto",
    "ImagesDto",
    "IndicatorColor",
    "IndicatorColors",
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
