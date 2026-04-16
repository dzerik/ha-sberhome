"""PairingAPI — endpoints для добавления новых устройств.

Endpoints (gateway/v1):
- `POST /devices/pairing` — поставить устройство в режим pairing.
- `GET /credentials/wifi` — получить WiFi-credentials для bootstrap нового устройства.
- `GET /devices/categories/matter` — список Matter-категорий.
- `POST /devices/matter/attestation` — Matter attestation (DAC/PAI).
- `POST /devices/matter/complete` — finalize Matter commissioning.
- `POST /devices/matter/noc` — выдать NOC сертификат.
- `POST /devices/matter/connect/controller` — connect controller flow.
- `POST /devices/matter/connect/device` — connect device flow.

Эти endpoints мало интересны для HA-интеграции (Matter имеет свой controller
в HA), но включены для полноты `aiosber` как standalone-пакета — для CLI-утилит,
скриптов автоматизации pairing.
"""

from __future__ import annotations

from typing import Any

from ..dto import DeviceToPairingBody
from ..transport import HttpTransport


class PairingAPI:
    """REST API for device pairing (Wi-Fi, Matter, Zigbee via hub)."""

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    # ----- generic pairing -----
    async def start_pairing(
        self,
        body: DeviceToPairingBody,
    ) -> dict[str, Any]:
        """Запустить pairing-flow для нового устройства.

        Параметры (image_set_type, pairing_type, timeout, ...) — в DTO body.
        """
        resp = await self._transport.post("/devices/pairing", json=body.to_dict())
        return _unwrap_dict(resp.json())

    async def get_wifi_credentials(self) -> dict[str, Any]:
        """Текущие WiFi-credentials для bootstrap (SSID + временный пароль)."""
        resp = await self._transport.get("/credentials/wifi")
        return _unwrap_dict(resp.json())

    # ----- Matter -----
    async def list_matter_categories(self) -> list[dict[str, Any]]:
        """Категории устройств, доступных через Matter pairing."""
        resp = await self._transport.get("/devices/categories/matter")
        return _unwrap_list(resp.json())

    async def matter_attestation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """DAC/PAI attestation step Matter commissioning."""
        resp = await self._transport.post("/devices/matter/attestation", json=payload)
        return _unwrap_dict(resp.json())

    async def matter_request_noc(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Запросить Node Operational Certificate для нового device."""
        resp = await self._transport.post("/devices/matter/noc", json=payload)
        return _unwrap_dict(resp.json())

    async def matter_complete(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Finalize commissioning."""
        resp = await self._transport.post("/devices/matter/complete", json=payload)
        return _unwrap_dict(resp.json())

    async def matter_connect_controller(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = await self._transport.post(
            "/devices/matter/connect/controller", json=payload
        )
        return _unwrap_dict(resp.json())

    async def matter_connect_device(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = await self._transport.post(
            "/devices/matter/connect/device", json=payload
        )
        return _unwrap_dict(resp.json())


# ----- helpers -----
def _unwrap_dict(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        return payload["result"]
    if isinstance(payload, dict):
        return payload
    raise ValueError(f"Expected dict, got {type(payload).__name__}")


def _unwrap_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "result" in payload and len(payload) <= 2:
        payload = payload["result"]
    if isinstance(payload, list):
        return payload
    raise ValueError(f"Expected list, got {type(payload).__name__}")


__all__ = ["PairingAPI"]
