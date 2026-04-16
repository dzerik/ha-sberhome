"""aiosber — async-клиент Sber Smart Home Gateway API.

Standalone-пакет, не зависит от Home Assistant. Может быть выделен в
отдельный PyPI-пакет одним поиск-заменой (`from .X` → `from aiosber.X`).

Источник истины протокола: wire-анализ протокола Sber wire-протокола.
См. `research_docs/` для полной спецификации.

Базовое использование (после готовности всех слоёв):

    from custom_components.sberhome.aiosber import (
        SberClient, AuthManager, InMemoryTokenStore,
        AttrKey, AttributeValueDto, ColorValue,
    )

    async with SberClient.from_token(token="...") as client:
        devices = await client.devices.list()
        await client.devices.set_state(
            device_id,
            [AttributeValueDto.of_bool(AttrKey.ON_OFF, True)],
        )
"""

from __future__ import annotations

from .api import DeviceAPI, GroupAPI, IndicatorAPI, PairingAPI, ScenarioAPI
from .client import SberClient
from .dto import (
    AttributeValueDto,
    AttributeValueType,
    AttrKey,
    ColorValue,
    DesiredDeviceStateDto,
    DesiredGroupStateDto,
    DeviceDto,
    SocketMessageDto,
    Topic,
)
from .dto.devices import TypedDevice, as_typed
from .exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
    PkceError,
    ProtocolError,
    RateLimitError,
    SberError,
)
from .transport import TopicRouter, WebSocketClient

__all__ = [
    "ApiError",
    "AttrKey",
    "AttributeValueDto",
    "AttributeValueType",
    "AuthError",
    "ColorValue",
    "DesiredDeviceStateDto",
    "DesiredGroupStateDto",
    "DeviceAPI",
    "DeviceDto",
    "GroupAPI",
    "IndicatorAPI",
    "InvalidGrant",
    "NetworkError",
    "PairingAPI",
    "PkceError",
    "ProtocolError",
    "RateLimitError",
    "SberClient",
    "ScenarioAPI",
    "SberError",
    "SocketMessageDto",
    "Topic",
    "TopicRouter",
    "TypedDevice",
    "WebSocketClient",
    "as_typed",
]
