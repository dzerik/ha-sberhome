"""Переклейка ``unique_id`` после смены облачного идентификатора.

``unique_id`` сущностей собирается из облачного ``id`` устройства. Облако меняет
его при пересоздании записи, и после переподключения устройство приходит с
новым ``id``.

Пока выбор устройств ломался вместе с ним, проблема была не видна: запись
устройства удалялась целиком, а Home Assistant каскадом стирал сущности —
установка «самолечилась» до пустоты. Теперь, когда выбор переживает смену
``id``, запись устройства остаётся жить, и без переклейки вышло бы хуже
прежнего: старые сущности остались бы навсегда недоступными, а новые получили
бы ``entity_id`` с суффиксом ``_2``, сломав все автоматизации пользователя.

Поэтому записи именно **переименовываются**. ``entity_id``, имя, область и
история остаются на месте — меняется только внутренний ключ.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN, LOGGER
from .identity import device_uid

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import SberHomeConfigEntry, SberHomeCoordinator


def _live_prefix(coordinator: SberHomeCoordinator, device_id: str) -> str:
    """Префикс ``unique_id``, который сущности этого устройства получат сейчас."""
    dto = coordinator.devices.get(device_id)
    return (dto.id if dto is not None and dto.id else None) or device_id


def _known_suffixes(coordinator: SberHomeCoordinator, device_id: str, prefix: str) -> list[str]:
    """Суффиксы сущностей устройства, от самого длинного к короткому.

    Порядок важен: иначе ``_power_state`` схлопнулось бы в ``_state`` и запись
    получила бы чужой ключ.
    """
    suffixes: set[str] = set()
    for entity in coordinator.entities.get(device_id, []):
        unique_id = getattr(entity, "unique_id", "") or ""
        if unique_id.startswith(f"{prefix}_"):
            suffixes.add(unique_id[len(prefix) + 1 :])
    return sorted(suffixes, key=len, reverse=True)


async def async_repair_rotated_unique_ids(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    coordinator: SberHomeCoordinator,
) -> int:
    """Переименовать ``unique_id`` сущностей, отставшие от текущего id устройства.

    Возвращает число переименованных записей.
    """
    try:
        from homeassistant.helpers import device_registry as dr
        from homeassistant.helpers import entity_registry as er

        enabled = coordinator.enabled_devices
        if not enabled:
            return 0

        device_reg = dr.async_get(hass)
        entity_reg = er.async_get(hass)
        renamed = 0

        for device_id, dto in enabled.items():
            uid = device_uid(dto, device_id)
            device_entry = device_reg.async_get_device(identifiers={(DOMAIN, uid)})
            if device_entry is None:
                continue

            live = _live_prefix(coordinator, device_id)
            suffixes = _known_suffixes(coordinator, device_id, live)

            for record in er.async_entries_for_device(
                entity_reg, device_entry.id, include_disabled_entities=True
            ):
                if record.config_entry_id != entry.entry_id:
                    continue
                if record.unique_id == live or record.unique_id.startswith(f"{live}_"):
                    continue

                target = _retarget(record.unique_id, live, suffixes)
                if target is None or target == record.unique_id:
                    continue
                # Занятый ключ — не наш случай: async_update_entity бросит, а
                # дубль лучше оставить видимым, чем уронить настройку.
                if entity_reg.async_get_entity_id(record.domain, DOMAIN, target):
                    continue

                entity_reg.async_update_entity(record.entity_id, new_unique_id=target)
                renamed += 1

        if renamed:
            LOGGER.info(
                "Переклеено %d сущностей: облако сменило идентификатор устройства",
                renamed,
            )
        return renamed
    except Exception:  # noqa: BLE001 — обслуживание не должно ронять setup
        LOGGER.warning("Переклейка идентификаторов сущностей не удалась", exc_info=True)
        return 0


def _retarget(unique_id: str, live: str, suffixes: list[str]) -> str | None:
    """Вычислить новый ``unique_id`` для отставшей записи.

    Суффиксы перебираются от длинного к короткому. Запись без суффикса — это
    основная сущность устройства, её ключ равен самому идентификатору.
    """
    for suffix in suffixes:
        if unique_id.endswith(f"_{suffix}"):
            return f"{live}_{suffix}"
    if "_" not in unique_id:
        return live
    return None


__all__ = ["async_repair_rotated_unique_ids"]
