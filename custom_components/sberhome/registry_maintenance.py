"""Device-registry maintenance — prune stale + удаление отвязанных устройств.

Вынесено из ``coordinator.py`` (SOLID-аудит: God Object; `_prune_stale_devices`
была самой сложной функцией кодовой базы — CC 18). Coordinator делегирует
сюда две операции:

- :func:`prune_stale_devices` — после каждого успешного refresh удаляет
  из HA device_registry устройства, пропавшие из Sber-аккаунта;
- :func:`remove_unlinked_devices` — при снятии галочки в панели убирает
  явно отвязанные устройства (иначе HA показывал бы orphan-записи вечно).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .aiosber import StateCache


# Suffix'ы unique_id, которые интеграция больше не выпускает. Убрать спеку из
# реестра фич недостаточно: запись в entity registry остаётся и показывается
# как «недоступно» — ровно это и случилось в 5.13.3 (issue #46).
#
# Чистка идёт по `endswith`, поэтому suffix обязан начинаться с `_`: иначе
# рискуем зацепить чужой ключ.
#
# ВНИМАНИЕ: это чёрный список, он работает на каждом старте. Если для какого-то
# ключа найдётся рабочий канал управления и сущность вернётся — строку отсюда
# ОБЯЗАТЕЛЬНО убрать, иначе новая сущность будет удаляться при каждой загрузке
# интеграции. Актуально для `staros_*`: шлюз ими только зеркалит настройки, но
# сама колонка отдаёт их по локальной сети, и запись там не исключена.
RETIRED_UNIQUE_ID_SUFFIXES: Final[tuple[str, ...]] = (
    # 5.13.3 — облако не отслеживает эти настройки, значения не живые.
    "_gamepad",
    "_staros_age_mode",
    "_staros_assistant_sounds_enabled",
)


def prune_stale_devices(
    hass: HomeAssistant,
    config_entry_id: str,
    state_cache: StateCache,
    enabled_device_ids: set[str] | None,
) -> None:
    """Удалить из device_registry устройства, пропавшие из Sber API.

    HA автоматически удалит привязанные entities вместе с DeviceEntry.
    Stale-детектор: DeviceEntry привязан к нашему config_entry_id, но его
    identifier не встречается ни в `state_cache` (serial_number / device_id),
    ни в whitelist'е виртуальных identifiers (home:/group:/indicator/
    scenarios — см. issue #25 / PR #26).

    Весь вызов обёрнут в try/except — если в моках недоступен реальный
    DeviceRegistry, coordinator refresh не валится.
    """
    try:
        from homeassistant.helpers import device_registry as dr

        device_reg = dr.async_get(hass)
        live_identifiers = _collect_live_identifiers(state_cache, enabled_device_ids)

        stale: list[str] = []
        for device in dr.async_entries_for_config_entry(device_reg, config_entry_id):
            our_idents = {ident for (domain, ident) in device.identifiers if domain == DOMAIN}
            if not our_idents:
                continue
            if our_idents.isdisjoint(live_identifiers):
                stale.append(device.id)

        for dev_reg_id in stale:
            device_reg.async_remove_device(dev_reg_id)
            LOGGER.info("Pruned stale device %s from registry", dev_reg_id)
    except Exception:  # noqa: BLE001 — best-effort, не ломаем refresh
        LOGGER.debug("Stale device pruning failed (ignored)", exc_info=True)


def _collect_live_identifiers(
    state_cache: StateCache,
    enabled_device_ids: set[str] | None,
) -> set[str]:
    """Собрать все identifiers, которые считаются «живыми».

    Реальные устройства (serial + device_id, с учётом enabled-фильтра)
    + виртуальные device_registry-записи, создаваемые вне sbermap:

    - ``home:{home.id}`` — NotifyEntity (notify.py);
    - ``group:{group_id}`` — SberGroupSwitch (switch_groups.py);
    - ``indicator`` — SberIndicatorLight (light.py);
    - ``scenarios`` — SberScenarioButton/switch/binary_sensor.

    Без whitelist'а виртуальные записи выпиливались prune'ом каждые
    несколько секунд, каскадно убивая entities (issue #25).
    """
    live: set[str] = set()
    for dev_id, dto in state_cache.get_all_devices().items():
        if enabled_device_ids is not None and dev_id not in enabled_device_ids:
            continue
        if dto.serial_number:
            live.add(dto.serial_number)
        if dto.id:
            live.add(dto.id)
        live.add(dev_id)

    for home in state_cache.get_homes():
        if home.id:
            live.add(f"home:{home.id}")

    for group_id in state_cache.get_all_groups():
        if group_id:
            live.add(f"group:{group_id}")

    live.add("indicator")
    live.add("scenarios")
    return live


def remove_unlinked_devices(
    hass: HomeAssistant,
    state_cache: StateCache,
    removed_ids: set[str],
) -> None:
    """Удалить из device_registry устройства, отвязанные пользователем.

    Вызывается из ``async_set_enabled_device_ids`` при снятии галочки в
    панели. DeviceInfo в entity.py использует `serial_number OR device_id`
    как identifier — пробуем оба варианта плюс сам sber_device_id.
    """
    if not removed_ids:
        return
    from homeassistant.helpers import device_registry as dr

    device_reg = dr.async_get(hass)
    for sber_device_id in removed_ids:
        dto = state_cache.get_device(sber_device_id)
        candidates: list[str] = []
        if dto is not None:
            if dto.serial_number:
                candidates.append(dto.serial_number)
            if dto.id:
                candidates.append(dto.id)
        candidates.append(sber_device_id)

        for ident in candidates:
            device_entry = device_reg.async_get_device(identifiers={(DOMAIN, ident)})
            if device_entry is not None:
                device_reg.async_remove_device(device_entry.id)
                LOGGER.info(
                    "Removed unlinked device %s (%s) from registry",
                    device_entry.name_by_user or device_entry.name,
                    sber_device_id,
                )
                break


def remove_retired_entities(hass: HomeAssistant, config_entry_id: str) -> int:
    """Убрать из entity_registry сущности, которые интеграция больше не создаёт.

    Вызывается на setup, до форварда платформ. Без этого пользователь после
    обновления видит устройство с серым списком: сущности не создаются кодом,
    но записи о них остаются, и HA показывает их как недоступные.

    Чистим строго по списку снятых ключей, а не «всё, чего нет в маппере»:
    нетривиальные платформы (light, climate, cover, fan, humidifier,
    media_player, vacuum, update) собирают сущности своими ветками, мимо
    ``map_device_to_entities``. Сравнение с ним вынесло бы их подчистую.

    Возвращает число удалённых записей (для лога и тестов).
    """
    try:
        from homeassistant.helpers import entity_registry as er

        entity_reg = er.async_get(hass)
        doomed = [
            entity.entity_id
            for entity in er.async_entries_for_config_entry(entity_reg, config_entry_id)
            if entity.unique_id.endswith(RETIRED_UNIQUE_ID_SUFFIXES)
        ]

        for entity_id in doomed:
            entity_reg.async_remove(entity_id)
            LOGGER.info("Removed retired entity %s from registry", entity_id)
        return len(doomed)
    except Exception:  # noqa: BLE001 — best-effort, не ломаем setup
        LOGGER.debug("Retired entity cleanup failed (ignored)", exc_info=True)
        return 0


__all__ = [
    "RETIRED_UNIQUE_ID_SUFFIXES",
    "prune_stale_devices",
    "remove_retired_entities",
    "remove_unlinked_devices",
]
