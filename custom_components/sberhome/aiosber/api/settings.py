"""StarosSettingsAPI — канал настроек колонок (companion.devices/v18/*).

Тонкий клиент поверх companion-`HttpTransport` (Authorization: Bearer). Никакой
бизнес-логики маппинга в HA-сущности — только вызовы + парсинг DTO. Маппинг
server-driven узлов в HA живёт в HA-слое (sbermap).

Особенности канала:
- Поле `screen` со значением null сервер не принимает — поэтому кладём его в
  тело запроса только когда оно действительно задано.
- Запись — `setting: [{type, id, value}]`, применяется на устройстве.
"""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from ..const import (
    COMPANION_STAROS_DEVICES_PATH,
    COMPANION_STAROS_SETTINGS_PATH,
    COMPANION_STAROS_SETTINGS_SET_PATH,
)
from ..dto.settings import SettingNodeDto, SettingScreenDto, StarosDeviceDto

if TYPE_CHECKING:
    from ..transport import HttpTransport

_MAX_SCREEN_DEPTH = 5


class StarosSettingsAPI:
    """Клиент канала настроек StarOS-устройств.

    Args:
        transport: companion-`HttpTransport` (base_url=COMPANION_BASE_URL,
            auth_header_name="Authorization", auth_header_prefix="Bearer ").
    """

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    async def list_devices(self) -> list[StarosDeviceDto]:
        """`POST /v18/devices` → список StarOS-устройств аккаунта."""
        resp = await self._transport.post(COMPANION_STAROS_DEVICES_PATH)
        payload = _safe_json(resp)
        raw = payload.get("devices") if isinstance(payload, dict) else None
        return [d for d in (StarosDeviceDto.from_dict(x) for x in (raw or [])) if d]

    async def get_settings(
        self, product: str, serial: str, *, screen: str | None = None
    ) -> SettingScreenDto | None:
        """`POST /v18/devices/settings` → server-driven экран настроек.

        `screen` кладётся в тело только если задан (значение null сервер не принимает).
        """
        body: dict[str, Any] = {"product": product, "serialNumber": serial}
        if screen is not None:
            body["screen"] = screen
        resp = await self._transport.post(COMPANION_STAROS_SETTINGS_PATH, json=body)
        return SettingScreenDto.from_dict(_safe_json(resp))

    async def get_settings_deep(self, product: str, serial: str) -> SettingScreenDto | None:
        """Экран настроек с раскрытыми подэкранами.

        Каждый CARD с `action=openScreen` раскрывается запросом `screen=<card.id>`,
        результат кладётся в `children` узла. Защита от циклов — `seen` по screen-id
        и ограничение глубины.
        """
        root = await self.get_settings(product, serial)
        if root is None:
            return None
        seen: set[str] = set()
        expanded = [
            await self._expand(product, serial, n, seen, depth=0) for n in root.settings
        ]
        return SettingScreenDto(header=root.header, settings=expanded)

    async def set_setting(
        self, product: str, serial: str, node_id: str, node_type: str, value: Any
    ) -> None:
        """`POST /v18/devices/settings/device` — записать одну настройку."""
        body = {
            "product": product,
            "serialNumber": serial,
            "setting": [{"type": node_type, "id": node_id, "value": value}],
        }
        await self._transport.post(COMPANION_STAROS_SETTINGS_SET_PATH, json=body)

    # ----- Internal -----
    async def _expand(
        self,
        product: str,
        serial: str,
        node: SettingNodeDto,
        seen: set[str],
        *,
        depth: int,
    ) -> SettingNodeDto:
        """Рекурсивно раскрыть CARD-подэкраны в children узла."""
        children = [
            await self._expand(product, serial, c, seen, depth=depth) for c in node.children
        ]
        node_id = node.id
        if (
            node.opens_screen
            and node_id
            and node_id not in seen
            and depth < _MAX_SCREEN_DEPTH
        ):
            seen.add(node_id)
            sub = await self.get_settings(product, serial, screen=node_id)
            if sub is not None:
                sub_children = [
                    await self._expand(product, serial, c, seen, depth=depth + 1)
                    for c in sub.settings
                ]
                children = [*children, *sub_children]
        return _with_children(node, children)


def _with_children(node: SettingNodeDto, children: list[SettingNodeDto]) -> SettingNodeDto:
    """frozen-copy узла с новыми children (dataclasses.replace без импорта)."""
    if children == node.children:
        return node
    return dataclasses.replace(node, children=children)


def _safe_json(resp: Any) -> Any:
    try:
        return resp.json()
    except (ValueError, AttributeError):
        return None


__all__ = ["StarosSettingsAPI"]
