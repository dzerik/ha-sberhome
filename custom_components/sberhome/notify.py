"""HA NotifyEntity platform — TTS surrogate per home.

🧪 EXPERIMENTAL. См. CHANGELOG v5.6.0 + spec. Каждый вызов делает 2-3
API request'а к облаку Sber (PUT scenario → POST /run). Не для частых
уведомлений (>1/мин). Concurrency control не делается — пользователь
явно принимает race condition при одновременных вызовах.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

if TYPE_CHECKING:
    from .aiosber.dto.union import UnionDto
    from .coordinator import SberHomeConfigEntry, SberHomeCoordinator
    from .ttc_surrogate import TtcSurrogateService
    from .tts_surrogate import TtsSurrogateService

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Регистрируем notify-entity для каждого Sber-дома: TTS (озвучить) и
    TTC (выполнить команду ассистенту)."""
    coord: SberHomeCoordinator = entry.runtime_data
    entities: list[NotifyEntity] = []
    for home in coord.state_cache.get_homes():
        if not home.id:
            continue
        entities.append(SberHomeTtsNotify(coord, coord.tts_service, home))
        entities.append(SberHomeTtcNotify(coord, coord.ttc_service, home))
    if not entities:
        _LOGGER.warning("Surrogate: no homes found — notify entities not registered")
    async_add_entities(entities)


class SberHomeTtsNotify(NotifyEntity):
    """🧪 EXPERIMENTAL — TTS surrogate через edit-then-run Sber-сценария.

    Каждый вызов делает 2-3 API request'а к облаку Sber. Не для частых
    уведомлений. См. CHANGELOG v5.6.0.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        tts_service: TtsSurrogateService,
        home: UnionDto,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._tts = tts_service
        self._home = home
        self._attr_unique_id = f"sber_tts_{home.id}"
        self._attr_name = f"Sber TTS ({home.name})"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"home:{self._home.id}")},
            manufacturer="Sber",
            model="Home",
            name=self._home.name or "",
        )

    async def async_send_message(
        self,
        message: str,
        title: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Произнести `message` через колонки дома.

        Resolution device_ids:
        - ``data.device_ids`` (list[str] raw Sber UUIDs) — приоритет.
        - Иначе — все Sber-колонки дома (через TtsSurrogateService).

        ``target`` (HA-style entity_id list) пока не резолвится — v5.6.0
        ограничивает scope. Warning логируется.
        """
        data = kwargs.get("data") or {}
        explicit_ids = data.get("device_ids") or []
        target = kwargs.get("target") or []
        if target:
            _LOGGER.warning(
                "TTS surrogate: 'target' parameter not yet supported in v5.6.0 — "
                "use 'data.device_ids' with raw Sber UUIDs instead. Falling back "
                "to all home speakers."
            )

        device_ids: list[str] | None = list(explicit_ids) if explicit_ids else None
        await self._tts.send(self._home.id, message, device_ids)


class SberHomeTtcNotify(NotifyEntity):
    """🧪 EXPERIMENTAL — TTC surrogate: колонка ВЫПОЛНЯЕТ текст как голосовую
    команду ассистенту («Расскажи анекдот», «Включи радио»), а не озвучивает.

    Каждый вызов делает 2-3 API request'а к Sber (edit-then-run). См. spec.
    """

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SberHomeCoordinator,
        ttc_service: TtcSurrogateService,
        home: UnionDto,
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._ttc = ttc_service
        self._home = home
        self._attr_unique_id = f"sber_ttc_{home.id}"
        self._attr_name = f"Sber команда ассистенту ({home.name})"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"home:{self._home.id}")},
            manufacturer="Sber",
            model="Home",
            name=self._home.name or "",
        )

    async def async_send_message(
        self,
        message: str,
        title: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Выполнить `message` как команду ассистенту на колонках дома.

        `message` — текст команды («Расскажи анекдот», «Поставь таймер на
        5 минут»). Resolution device_ids: ``data.device_ids`` (raw Sber UUID)
        → иначе все колонки дома.
        """
        data = kwargs.get("data") or {}
        explicit_ids = data.get("device_ids") or []
        if kwargs.get("target"):
            _LOGGER.warning(
                "TTC surrogate: 'target' не поддержан — используйте "
                "'data.device_ids' с raw Sber UUID. Fallback на все колонки дома."
            )
        device_ids: list[str] | None = list(explicit_ids) if explicit_ids else None
        await self._ttc.send(self._home.id, message, device_ids)
