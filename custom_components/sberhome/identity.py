"""Идентичность устройства: один ключ вместо двух.

Устройство Сбера описывается двумя разными идентификаторами, и раньше они
использовались вперемешку:

- ``serial_number`` — идентификатор железа, он же ``external_id``. Переживает
  переподключение устройства.
- ``id`` — номер записи в облаке. При удалении хаба записи его устройств
  стираются, и при повторном подключении облако выдаёт **новый** ``id``.

Реестр устройств Home Assistant всегда ключевался серийником (см. ``entity.py``,
``device_info``), а список выбранных пользователем устройств хранил облачные
``id``. После переподключения сохранённый ``id`` не совпадал ни с чем: устройство
переставало считаться выбранным, сущности не создавались, а обслуживание реестра
дополнительно удаляло запись устройства на каждом опросе.

Здесь собраны чистые функции, задающие единое правило. Никаких побочных
эффектов, никаких импортов Home Assistant — чтобы правило было ровно одно и его
можно было проверить тестом.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from .aiosber.dto.device import DeviceDto


def device_uid(dto: DeviceDto | None, fallback: str) -> str:
    """Стабильный идентификатор устройства.

    Порядок повторяет ``entity.py`` буквально: то, что кладётся в
    ``DeviceInfo.identifiers``, и то, чем ключуется выбор, обязано совпадать.
    Расхождение этих двух правил и было причиной всей истории.
    """
    if dto is not None:
        if dto.serial_number:
            return dto.serial_number
        if dto.id:
            return dto.id
    return fallback


def device_match_keys(dto: DeviceDto | None, device_id: str) -> set[str]:
    """Все идентификаторы, по которым устройство допустимо опознать.

    Нужны для обратной совместимости: сохранённый выбор может быть как в новом
    формате (серийник), так и в старом (облачный ``id``), а ключ кэша может
    отличаться от обоих.
    """
    keys = {device_id}
    if dto is not None:
        if dto.serial_number:
            keys.add(dto.serial_number)
        if dto.id:
            keys.add(dto.id)
    return keys


def build_uid_index(
    devices: Mapping[str, DeviceDto],
) -> tuple[dict[str, list[str]], set[str]]:
    """Сопоставить uid → device_id и выделить неоднозначные uid.

    Один серийник может встретиться у двух записей: мультиэндпоинтные
    устройства, дети моста, не удалённая старая запись в облаке. Такие uid
    помечаются как неоднозначные и обрабатываются отдельно — иначе один
    сохранённый серийник включил бы сразу оба устройства, то есть протащил бы в
    Home Assistant то, чего пользователь не выбирал.
    """
    index: dict[str, list[str]] = {}
    for device_id, dto in devices.items():
        index.setdefault(device_uid(dto, device_id), []).append(device_id)

    ambiguous = {uid for uid, ids in index.items() if len(ids) > 1}
    return index, ambiguous


def _freshness(dto: DeviceDto | None) -> str:
    """Насколько свежие данные у записи — по самой поздней метке синхронизации.

    Метки в ISO-8601 с одинаковым форматом, поэтому сравнение строк корректно.
    Служит только для выбора победителя среди записей с одним серийником:
    живая запись почти всегда свежее забытой в облаке.
    """
    if dto is None:
        return ""
    return max((av.last_sync or "" for av in dto.reported_state), default="")


def _pick_one(
    device_ids: list[str],
    devices: Mapping[str, DeviceDto],
    stored: set[str],
) -> str:
    """Выбрать ровно одно устройство среди записей с общим uid.

    Порядок предпочтения: запись, чей облачный id пользователь выбирал явно →
    самая свежая по меткам синхронизации → лексикографически наибольший id.
    Последний критерий нужен лишь для того, чтобы результат был устойчивым:
    выбор не должен прыгать между опросами.
    """
    explicit = [
        did
        for did in device_ids
        if did in stored
        or ((dto := devices.get(did)) is not None and dto.id is not None and dto.id in stored)
    ]
    pool = explicit or device_ids
    return max(pool, key=lambda did: (_freshness(devices.get(did)), did))


def resolve_enabled_ids(
    devices: Mapping[str, DeviceDto],
    stored: Iterable[str] | None,
) -> set[str] | None:
    """Сохранённый выбор → множество *текущих* ключей кэша.

    ``None`` на входе означает «выбор не настроен» и проходит насквозь: это
    старые установки, которым показывалось всё, и превращать их молчанием в
    пустой выбор нельзя — у пользователя разом исчезли бы все устройства.

    Сопоставление идёт по любому из ключей устройства, поэтому старый формат
    хранения продолжает работать до, во время и после миграции.
    """
    if stored is None:
        return None

    stored_set = set(stored)
    if not stored_set:
        return set()

    index, ambiguous = build_uid_index(devices)

    enabled: set[str] = set()
    for uid, device_ids in index.items():
        if uid in ambiguous:
            hit = any(device_match_keys(devices.get(did), did) & stored_set for did in device_ids)
            if hit:
                enabled.add(_pick_one(device_ids, devices, stored_set))
            continue

        device_id = device_ids[0]
        if device_match_keys(devices.get(device_id), device_id) & stored_set:
            enabled.add(device_id)

    return enabled


def to_uids(
    devices: Mapping[str, DeviceDto],
    selected: Iterable[str],
) -> list[str]:
    """Перевести выбор в стабильный формат хранения.

    Значения, которые не удалось сопоставить ни с одним устройством, переносятся
    как есть: устройство может быть офлайн или просто отсутствовать в этой
    выдаче, а молчаливая потеря выбора — ровно та ошибка, которую мы чиним.

    Для устройств с неоднозначным uid записывается облачный ``id``: он разводит
    коллизию однозначно, ценой того, что такое устройство не переживёт
    переподключение. Это лучше, чем включить вместе с ним чужое.
    """
    index, ambiguous = build_uid_index(devices)
    by_key: dict[str, str] = {}
    for uid, device_ids in index.items():
        for device_id in device_ids:
            dto = devices.get(device_id)
            target = (dto.id or device_id) if (uid in ambiguous and dto is not None) else uid
            for key in device_match_keys(dto, device_id):
                by_key.setdefault(key, target)

    result: list[str] = []
    for value in selected:
        mapped = by_key.get(value, value)
        if mapped not in result:
            result.append(mapped)
    return sorted(result)


__all__ = [
    "build_uid_index",
    "device_match_keys",
    "device_uid",
    "resolve_enabled_ids",
    "to_uids",
]
