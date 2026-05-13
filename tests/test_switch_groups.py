"""Tests for SberGroupSwitch (v5.4.0)."""

from __future__ import annotations

from dataclasses import replace as _replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto import (
    AttributeValueDto,
    AttributeValueType,
    DeviceDto,
)
from custom_components.sberhome.aiosber.dto.union import (
    UnionDto,
    UnionType,
)
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.switch_groups import SberGroupSwitch


def _dev(id_: str, *, online: bool = True, on: bool | None = None) -> DeviceDto:
    """Helper: device с online + on_off в reported_state."""
    rs = [
        AttributeValueDto(key="online", type=AttributeValueType.BOOL, bool_value=online),
    ]
    if on is not None:
        rs.append(AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=on))
    return DeviceDto(id=id_, reported_state=rs)


def _make_coord(*, group_id: str, group_name: str, devices: list[DeviceDto]) -> MagicMock:
    cache = StateCache()
    devices_with_groups = [_replace(d, group_ids=[group_id]) for d in devices]
    cache.update_from_flat(
        homes=[],
        rooms=[],
        groups=[UnionDto(id=group_id, name=group_name, group_type=UnionType.GROUP)],
        devices=devices_with_groups,
    )
    # No private mutation needed — reverse-index built by update_from_flat.

    coord = MagicMock()
    coord.state_cache = cache
    coord.client = MagicMock()
    coord.client.groups = MagicMock()
    coord.client.groups.set_state = AsyncMock()
    return coord


def test_group_switch_aggregated_is_on_when_any_device_on():
    coord = _make_coord(
        group_id="grp-1",
        group_name="Освещение прихожей",
        devices=[_dev("d1", on=False), _dev("d2", on=True), _dev("d3", on=False)],
    )
    sw = SberGroupSwitch(coord, "grp-1")
    assert sw.is_on is True


def test_group_switch_all_off():
    coord = _make_coord(
        group_id="grp-1",
        group_name="X",
        devices=[_dev("d1", on=False), _dev("d2", on=False)],
    )
    sw = SberGroupSwitch(coord, "grp-1")
    assert sw.is_on is False


def test_group_switch_is_on_none_when_no_on_off_devices():
    """Группа только из устройств без on_off (cover-only) → is_on = None."""
    coord = _make_coord(
        group_id="grp-1",
        group_name="Шторы",
        devices=[_dev("d1"), _dev("d2")],
    )
    sw = SberGroupSwitch(coord, "grp-1")
    assert sw.is_on is None


def test_group_switch_unavailable_when_all_offline():
    coord = _make_coord(
        group_id="grp-1",
        group_name="X",
        devices=[_dev("d1", online=False, on=True), _dev("d2", online=False, on=False)],
    )
    sw = SberGroupSwitch(coord, "grp-1")
    assert sw.available is False


@pytest.mark.asyncio
async def test_group_switch_turn_on_calls_group_set_state():
    """turn_on вызывает GroupAPI.set_state ровно один раз, НЕ перебирает devices."""
    coord = _make_coord(
        group_id="grp-1",
        group_name="X",
        devices=[_dev("d1", on=False), _dev("d2", on=False)],
    )
    sw = SberGroupSwitch(coord, "grp-1")
    sw.async_write_ha_state = MagicMock()

    await sw.async_turn_on()

    coord.client.groups.set_state.assert_awaited_once()
    call_args = coord.client.groups.set_state.await_args.args
    assert call_args[0] == "grp-1"
    sent_attrs = call_args[1]
    assert len(sent_attrs) == 1
    assert sent_attrs[0].key == "on_off"
    assert sent_attrs[0].bool_value is True


@pytest.mark.asyncio
async def test_group_switch_optimistic_patch_after_turn_on():
    """После turn_on каждому device группы patch'ится desired on_off=True."""
    coord = _make_coord(
        group_id="grp-1",
        group_name="X",
        devices=[_dev("d1", on=False), _dev("d2", on=False)],
    )
    sw = SberGroupSwitch(coord, "grp-1")
    sw.async_write_ha_state = MagicMock()

    await sw.async_turn_on()

    # У каждого device теперь desired_state на on_off=True
    for did in ["d1", "d2"]:
        dto = coord.state_cache.get_device(did)
        desired = {av.key: av for av in dto.desired_state}
        assert "on_off" in desired
        assert desired["on_off"].bool_value is True


@pytest.mark.asyncio
async def test_switch_platform_includes_group_switches():
    """async_setup_entry форвардит SberGroupSwitch для каждой непустой Sber-group."""
    from custom_components.sberhome.switch import async_setup_entry

    coord = _make_coord(
        group_id="grp-1",
        group_name="Освещение прихожей",
        devices=[_dev("d1", on=False)],
    )
    coord.devices = coord.state_cache.get_all_devices()
    coord.entities = {}  # пустые entities — никаких device-switches

    hass = MagicMock()
    entry = MagicMock()
    entry.runtime_data = coord
    added = []

    def fake_add(entities, _update_before_add=True):
        added.extend(entities)

    await async_setup_entry(hass, entry, fake_add)
    group_switches = [e for e in added if isinstance(e, SberGroupSwitch)]
    assert len(group_switches) == 1
    assert group_switches[0].unique_id == "sber_group_grp-1"


@pytest.mark.asyncio
async def test_empty_group_not_exposed():
    """Группа без устройств не создаёт SberGroupSwitch."""
    from custom_components.sberhome.switch import async_setup_entry

    cache = StateCache()
    cache.update_from_flat(
        homes=[],
        rooms=[],
        groups=[UnionDto(id="grp-empty", name="Пусто", group_type=UnionType.GROUP)],
        devices=[],
    )
    coord = MagicMock()
    coord.state_cache = cache
    coord.devices = {}
    coord.entities = {}

    hass = MagicMock()
    entry = MagicMock()
    entry.runtime_data = coord
    added = []

    def fake_add(entities, _update_before_add=True):
        added.extend(entities)

    await async_setup_entry(hass, entry, fake_add)
    group_switches = [e for e in added if isinstance(e, SberGroupSwitch)]
    assert group_switches == []
