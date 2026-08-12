"""Обслуживание реестра устройств.

Удаление записи устройства уносит каскадом все его сущности вместе с историей и
ссылками из автоматизаций. Поводов ошибиться много: облако может не отдать
устройство в конкретной выдаче, запасной путь опроса возвращает только дом по
умолчанию, список может быть усечён по размеру страницы.

Отсюда два режима, и тесты держат границу между ними: снятое пользователем
удаляется сразу, просто пропавшее — только после нескольких промахов подряд и
только если выдаче можно доверять.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.const import DOMAIN, PRUNE_MIN_CONSECUTIVE_MISSES
from custom_components.sberhome.registry_maintenance import prune_stale_devices

SERIAL = "SER-1"
OLD_ID = "cloud-old"
NEW_ID = "cloud-new"


def _dto(device_id: str, serial: str | None = SERIAL) -> DeviceDto:
    payload: dict = {"id": device_id, "name": {"name": device_id}}
    if serial:
        payload["serial_number"] = serial
    return DeviceDto.from_dict(payload)


def _cache(devices: dict[str, DeviceDto]) -> MagicMock:
    cache = MagicMock()
    cache.get_all_devices.return_value = devices
    cache.get_homes.return_value = []
    cache.get_all_groups.return_value = {}
    return cache


def _entry(identifier: str) -> MagicMock:
    entry = MagicMock()
    entry.id = f"reg-{identifier}"
    entry.identifiers = {(DOMAIN, identifier)}
    return entry


def _run(cache, enabled, entries, *, degraded=False, counters=None, times=1) -> MagicMock:
    device_reg = MagicMock()
    for _ in range(times):
        with (
            patch("homeassistant.helpers.device_registry.async_get", return_value=device_reg),
            patch(
                "homeassistant.helpers.device_registry.async_entries_for_config_entry",
                return_value=entries,
            ),
        ):
            prune_stale_devices(
                MagicMock(),
                "entry-1",
                cache,
                enabled,
                degraded=degraded,
                miss_counters=counters if counters is not None else {},
            )
    return device_reg


def test_reconnected_device_is_not_pruned() -> None:
    """Главный регресс: устройство переподключили, облако дало новый id.

    Раньше сохранённый выбор переставал совпадать, устройство считалось
    невыбранным, и запись сносилась на каждом опросе вместе с сущностями.
    Серийник не менялся — запись обязана выжить.
    """
    cache = _cache({NEW_ID: _dto(NEW_ID)})
    device_reg = _run(cache, {NEW_ID}, [_entry(SERIAL)], times=PRUNE_MIN_CONSECUTIVE_MISSES + 2)

    device_reg.async_remove_device.assert_not_called()


def test_opted_out_device_is_pruned_immediately() -> None:
    """Снял галочку — решение осознанное, тянуть незачем.

    Отсрочка здесь была бы вредна: пользователь ждёт, что устройство исчезнет
    сразу, а не через несколько опросов.
    """
    cache = _cache({"dev-1": _dto("dev-1", "S1"), "dev-2": _dto("dev-2", "S2")})
    device_reg = _run(cache, {"dev-1"}, [_entry("S2")])

    device_reg.async_remove_device.assert_called_once_with("reg-S2")


def test_missing_device_requires_consecutive_misses() -> None:
    counters: dict[str, int] = {}
    cache = _cache({})
    entries = [_entry("ghost")]

    device_reg = _run(cache, set(), entries, counters=counters, times=1)
    device_reg.async_remove_device.assert_not_called()

    device_reg = _run(
        cache, set(), entries, counters=counters, times=PRUNE_MIN_CONSECUTIVE_MISSES - 1
    )
    device_reg.async_remove_device.assert_called_once_with("reg-ghost")


def test_miss_counter_resets_when_device_returns() -> None:
    """Нестабильная связь не должна накапливать приговор."""
    counters: dict[str, int] = {}
    entries = [_entry(SERIAL)]

    _run(_cache({}), set(), entries, counters=counters, times=PRUNE_MIN_CONSECUTIVE_MISSES - 1)
    _run(_cache({NEW_ID: _dto(NEW_ID)}), {NEW_ID}, entries, counters=counters)
    device_reg = _run(
        _cache({}), set(), entries, counters=counters, times=PRUNE_MIN_CONSECUTIVE_MISSES - 1
    )

    device_reg.async_remove_device.assert_not_called()


def test_degraded_refresh_never_prunes_missing() -> None:
    """Неполной выдаче верить нельзя, сколько бы опросов ни прошло."""
    counters: dict[str, int] = {}
    device_reg = _run(
        _cache({}),
        set(),
        [_entry("ghost")],
        degraded=True,
        counters=counters,
        times=PRUNE_MIN_CONSECUTIVE_MISSES * 3,
    )

    device_reg.async_remove_device.assert_not_called()
    assert counters == {}


def test_degraded_refresh_still_removes_opted_out() -> None:
    """Снятое пользователем от качества выдачи не зависит."""
    cache = _cache({"dev-1": _dto("dev-1", "S1")})
    device_reg = _run(cache, set(), [_entry("S1")], degraded=True)

    device_reg.async_remove_device.assert_called_once_with("reg-S1")


def test_virtual_entries_survive() -> None:
    """Дома, группы, индикатор и сценарии живут вне реестра устройств.

    Без явного исключения чистка выпиливала бы их каждые несколько секунд,
    каскадно убивая сущности.
    """
    cache = _cache({})
    cache.get_homes.return_value = [MagicMock(id="home-1")]
    cache.get_all_groups.return_value = {"grp-1": MagicMock()}
    entries = [
        _entry("home:home-1"),
        _entry("group:grp-1"),
        _entry("indicator"),
        _entry("scenarios"),
    ]

    device_reg = _run(cache, set(), entries, times=PRUNE_MIN_CONSECUTIVE_MISSES + 1)

    device_reg.async_remove_device.assert_not_called()


def test_passthrough_mode_keeps_everything() -> None:
    """Выбор не настроен — значит выбранными считаются все."""
    cache = _cache({"dev-1": _dto("dev-1", "S1")})
    device_reg = _run(cache, None, [_entry("S1")], times=PRUNE_MIN_CONSECUTIVE_MISSES + 1)

    device_reg.async_remove_device.assert_not_called()


def test_failure_is_visible(caplog: pytest.LogCaptureFixture) -> None:
    """Сбой обслуживания обязан быть слышен.

    Раньше он уходил в отладочный лог: чистка могла годами не работать, и
    выглядело это ровно как работающая чистка.
    """
    cache = _cache({})
    device_reg = MagicMock()
    device_reg.async_remove_device.side_effect = RuntimeError("реестр недоступен")

    with (
        patch("homeassistant.helpers.device_registry.async_get", return_value=device_reg),
        patch(
            "homeassistant.helpers.device_registry.async_entries_for_config_entry",
            return_value=[_entry("ghost")],
        ),
        caplog.at_level(logging.WARNING),
        pytest.raises(RuntimeError),
    ):
        prune_stale_devices(
            MagicMock(),
            "entry-1",
            cache,
            set(),
            miss_counters={"ghost": PRUNE_MIN_CONSECUTIVE_MISSES - 1},
        )

    assert "Обслуживание реестра" in caplog.text
