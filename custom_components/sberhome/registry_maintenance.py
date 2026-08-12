"""Обслуживание реестра устройств: удаление пропавших и отвязанных.

Coordinator делегирует сюда две операции:

- :func:`prune_stale_devices` — после каждого успешного опроса убирает записи
  устройств, которых больше нет в аккаунте;
- :func:`remove_unlinked_devices` — при снятии галочки в панели убирает явно
  отвязанное устройство, иначе Home Assistant показывал бы его вечно.

Здесь легко навредить сильнее, чем помочь: удаление записи устройства уносит
каскадом все его сущности вместе с историей и ссылками из автоматизаций. А
поводов ошибиться много — облако может не отдать устройство в конкретной
выдаче, запасной путь опроса возвращает только дом по умолчанию, список
устройств может быть усечён по размеру страницы. Раньше любого из этих поводов
хватало, чтобы стереть исправное устройство.

Поэтому два разных режима. Устройство, которое пользователь снял в панели,
удаляется сразу: это его осознанное решение, и тянуть незачем. Устройство,
которое просто пропало из выдачи, удаляется только после нескольких промахов
подряд, и не удаляется вовсе, если выдаче нельзя доверять.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .const import DOMAIN, LOGGER, PRUNE_MIN_CONSECUTIVE_MISSES
from .identity import device_match_keys

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .aiosber import StateCache


def prune_stale_devices(
    hass: HomeAssistant,
    config_entry_id: str,
    state_cache: StateCache,
    enabled_device_ids: set[str] | None,
    *,
    degraded: bool = False,
    miss_counters: dict[str, int] | None = None,
) -> int:
    """Убрать из реестра записи, которым там больше не место.

    ``degraded`` означает «выдаче нельзя доверять целиком»: в этом случае
    пропавшие устройства не трогаем вовсе, а счётчики промахов не двигаем,
    чтобы сетевой сбой не приближал удаление.

    Возвращает число удалённых записей. Ошибки не пробрасываются — обслуживание
    не должно ронять опрос, — но и не замалчиваются: раньше сбой уходил в
    отладочный лог, и годами неработающая чистка выглядела как работающая.
    """
    counters = miss_counters if miss_counters is not None else {}
    try:
        from homeassistant.helpers import device_registry as dr

        device_reg = dr.async_get(hass)
        live, opted_out = _collect_identifiers(state_cache, enabled_device_ids)

        doomed: list[tuple[str, str]] = []
        for device in dr.async_entries_for_config_entry(device_reg, config_entry_id):
            our_idents = {ident for (domain, ident) in device.identifiers if domain == DOMAIN}
            if not our_idents:
                continue

            if not our_idents.isdisjoint(live):
                # Устройство на месте — сбрасываем накопленные промахи.
                for ident in our_idents:
                    counters.pop(ident, None)
                continue

            if not our_idents.isdisjoint(opted_out):
                # Снято пользователем в панели — решение осознанное, ждать нечего.
                doomed.append((device.id, "снято в панели"))
                continue

            if degraded:
                # Выдача неполная: отсутствие устройства ничего не доказывает.
                continue

            key = sorted(our_idents)[0]
            counters[key] = counters.get(key, 0) + 1
            if counters[key] >= PRUNE_MIN_CONSECUTIVE_MISSES:
                doomed.append((device.id, "пропало из аккаунта"))
                counters.pop(key, None)

        for dev_reg_id, reason in doomed:
            device_reg.async_remove_device(dev_reg_id)
            LOGGER.info("Удалена запись устройства %s (%s)", dev_reg_id, reason)
        return len(doomed)
    except Exception:
        LOGGER.warning(
            "Обслуживание реестра устройств не выполнено — записи могли устареть",
            exc_info=True,
        )
        raise


def _collect_identifiers(
    state_cache: StateCache,
    enabled_device_ids: set[str] | None,
) -> tuple[set[str], set[str]]:
    """Разделить идентификаторы на «живые» и «снятые пользователем».

    Разница принципиальная. Живые не трогаем. Снятые удаляем сразу. Всё
    остальное — это устройства, которых в выдаче не оказалось: они не попадают
    ни в одно из множеств и проходят через отсрочку.

    В живые попадают и виртуальные записи, создаваемые вне реестра устройств:
    дома, группы, индикатор и сценарии. Без них чистка выпиливала бы их каждые
    несколько секунд, каскадно убивая сущности.
    """
    live: set[str] = set()
    opted_out: set[str] = set()

    for dev_id, dto in state_cache.get_all_devices().items():
        keys = device_match_keys(dto, dev_id)
        if enabled_device_ids is not None and dev_id not in enabled_device_ids:
            opted_out |= keys
        else:
            live |= keys

    for home in state_cache.get_homes():
        if home.id:
            live.add(f"home:{home.id}")

    for group_id in state_cache.get_all_groups():
        if group_id:
            live.add(f"group:{group_id}")

    live.add("indicator")
    live.add("scenarios")

    # Устройство могло попасть в оба множества, если серийник делят выбранная и
    # невыбранная записи. Живое важнее: лучше оставить лишнее, чем стереть нужное.
    return live, opted_out - live


def remove_unlinked_devices(
    hass: HomeAssistant,
    state_cache: StateCache,
    removed_ids: set[str],
) -> None:
    """Удалить из реестра устройства, отвязанные пользователем.

    Вызывается при снятии галочки в панели. Реестр ключуется серийником, но на
    входе может прийти любой известный идентификатор устройства, поэтому
    перебираем все.
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
                    "Отвязанное устройство %s (%s) убрано из реестра",
                    device_entry.name_by_user or device_entry.name,
                    sber_device_id,
                )
                break


__all__ = ["prune_stale_devices", "remove_unlinked_devices"]
