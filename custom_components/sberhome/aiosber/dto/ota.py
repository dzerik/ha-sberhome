"""OtaUpdateInfoDto — информация об OTA-обновлении прошивки.

JSON schema: поле ``fw_task_status`` в SocketMessageDto (WS topic INVENTORY_OTA).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Self

from ._serde import dataclass_to_dict, from_dict


@dataclass(slots=True, frozen=True)
class OtaUpdateInfoDto:
    """OTA firmware update information from WS push."""

    id: str | None = None
    meta: dict[str, Any] | None = None
    firmware_id: str | None = None
    confirmation_status: str | None = None
    update_status: str | None = None
    device_external_id: str | None = None
    device_name: str | None = None
    device_photo: str | None = None
    routing_key: str | None = None
    started_at: str | None = None
    retry_count: int | None = None
    percent: int | None = None
    error: str | None = None
    version: str | None = None
    description: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Self | None:
        if data is None:
            return None
        return from_dict(cls, data)

    def to_dict(self) -> dict[str, Any]:
        return dataclass_to_dict(self)


__all__ = ["OtaUpdateInfoDto"]
