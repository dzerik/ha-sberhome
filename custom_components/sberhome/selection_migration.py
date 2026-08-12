"""Перевод выбора устройств на стабильный ключ.

Раньше выбор хранился облачными ``id``. Облако меняет ``id`` при пересоздании
записи устройства — например, когда удалили хаб и подключили его заново. После
этого сохранённый выбор не совпадал ни с чем, устройство переставало считаться
выбранным, и все его сущности пропадали.

Миграция переводит сохранённые значения в серийники. Делается это не в
``async_migrate_entry``: там нет ни сети, ни кэша устройств, а без них
сопоставить ``id`` с серийником не из чего. Поэтому — на setup, сразу после
первого успешного опроса.

Главное правило: **при малейшем сомнении ничего не писать**. Неверная запись
здесь стоит пользователю всех его сущностей, а отложенная миграция не стоит
ничего: она повторится на следующем пригодном опросе.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import (
    CONF_ENABLED_DEVICE_IDS,
    CONF_ENABLED_DEVICE_UIDS,
    CONF_SELECTION_MIRROR,
    CONF_SELECTION_SCHEMA,
    LOGGER,
    SELECTION_SCHEMA_VERSION,
)
from .identity import resolve_enabled_ids, to_uids

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .coordinator import SberHomeConfigEntry, SberHomeCoordinator


def _refresh_is_usable(coordinator: SberHomeCoordinator) -> bool:
    """Можно ли доверять текущей выдаче настолько, чтобы переписать выбор.

    Пустой кэш — очевидный отказ. Признак неполной выдачи выставляет слой
    работы с API: запасной путь опроса возвращает только дом по умолчанию, а
    список устройств может быть усечён по размеру страницы. Мигрировать по
    такой выдаче значит потерять выбор для устройств, которых в ней не было.
    """
    if not coordinator.state_cache.get_all_devices():
        return False
    client = getattr(coordinator, "client", None)
    service = getattr(client, "device_service", None) if client is not None else None
    return not getattr(service, "last_refresh_degraded", False)


async def async_migrate_selection(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    coordinator: SberHomeCoordinator,
) -> bool:
    """Привести выбор устройств к стабильному формату.

    Возвращает True, если работа завершена и повторять её не нужно.
    """
    options = entry.options
    has_new = CONF_ENABLED_DEVICE_UIDS in options
    has_legacy = CONF_ENABLED_DEVICE_IDS in options

    # Выбор не настраивался — установка живёт в режиме «показывать всё».
    # Любая запись превратила бы это в конкретный список и мгновенно скрыла у
    # такого пользователя все устройства. Самая дорогая из возможных регрессий.
    if not has_new and not has_legacy:
        return True

    if has_new:
        return await _reconcile_external_write(hass, entry, coordinator)

    legacy = list(options[CONF_ENABLED_DEVICE_IDS])

    # Явно выбрано ничего — переводить нечего, но формат зафиксировать стоит.
    if not legacy:
        _write(hass, entry, uids=[], mirror=[])
        return True

    if not _refresh_is_usable(coordinator):
        LOGGER.info(
            "Перевод выбора устройств на стабильный ключ отложен: выдача неполная. "
            "Повторим после следующего успешного опроса"
        )
        return False

    devices = coordinator.devices
    uids = to_uids(devices, legacy)
    mirror = sorted(resolve_enabled_ids(devices, uids) or set())
    _write(hass, entry, uids=uids, mirror=mirror)
    LOGGER.info(
        "Выбор устройств переведён на стабильный ключ: %d значений, сопоставлено %d",
        len(uids),
        len(mirror),
    )
    return True


async def _reconcile_external_write(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    coordinator: SberHomeCoordinator,
) -> bool:
    """Учесть выбор, сделанный версией интеграции без стабильного ключа.

    Пользователь мог откатиться через HACS, поменять выбор там и вернуться. Та
    версия пишет только старый ключ. Отличаем это по копии зеркала: если
    старый ключ разошёлся с ней, значит его писали не мы, и он авторитетен
    целиком — включая снятые галочки. Иначе воскрешали бы устройства, которые
    пользователь отключил.
    """
    options = entry.options
    legacy = options.get(CONF_ENABLED_DEVICE_IDS)
    mirror = options.get(CONF_SELECTION_MIRROR)

    if legacy is None or mirror is None or sorted(legacy) == sorted(mirror):
        return True

    if not _refresh_is_usable(coordinator):
        return False

    devices = coordinator.devices
    uids = to_uids(devices, list(legacy))
    new_mirror = sorted(resolve_enabled_ids(devices, uids) or set())
    _write(hass, entry, uids=uids, mirror=new_mirror)
    LOGGER.info(
        "Выбор устройств изменялся другой версией интеграции — принят как есть (%d значений)",
        len(uids),
    )
    return True


def _write(
    hass: HomeAssistant,
    entry: SberHomeConfigEntry,
    *,
    uids: list[str],
    mirror: list[str],
) -> None:
    """Записать выбор во все три ключа разом.

    Зеркало из текущих облачных ``id`` существует ради отката интеграции на
    предыдущую версию: та прочитает привычный ей ключ и продолжит работать.
    """
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_ENABLED_DEVICE_UIDS: uids,
            CONF_ENABLED_DEVICE_IDS: mirror,
            CONF_SELECTION_MIRROR: mirror,
            CONF_SELECTION_SCHEMA: SELECTION_SCHEMA_VERSION,
        },
    )


__all__ = ["async_migrate_selection"]
