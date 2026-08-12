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

from typing import TYPE_CHECKING

from .const import DOMAIN, LOGGER

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .aiosber import StateCache


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


__all__ = ["prune_stale_devices", "remove_unlinked_devices"]
