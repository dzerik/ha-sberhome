"""Tests for DeviceService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto import AttributeValueDto, DeviceDto
from custom_components.sberhome.aiosber.dto.union import UnionDto, UnionTreeDto, UnionType
from custom_components.sberhome.aiosber.service.device_service import DeviceService
from custom_components.sberhome.aiosber.service.state_cache import StateCache


def _make_cache() -> StateCache:
    cache = StateCache()
    tree = UnionTreeDto(
        union=UnionDto(id="home", group_type=UnionType.HOME),
        devices=[],
        children=[
            UnionTreeDto(
                union=UnionDto(id="r1", name="Кухня", group_type=UnionType.ROOM),
                devices=[
                    DeviceDto(
                        id="d1",
                        image_set_type="bulb_sber",
                        reported_state=[AttributeValueDto.of_bool("on_off", True)],
                    ),
                    DeviceDto(id="d2", image_set_type="cat_socket"),
                ],
                children=[],
            ),
            UnionTreeDto(
                union=UnionDto(id="r2", name="Зал", group_type=UnionType.ROOM),
                devices=[DeviceDto(id="d3", image_set_type="bulb_sber")],
                children=[],
            ),
        ],
    )
    cache.update_from_tree(tree)
    return cache


def test_get():
    cache = _make_cache()
    svc = DeviceService(api=MagicMock(), cache=cache)
    assert svc.get("d1") is not None
    assert svc.get("nonexistent") is None


def test_list_all():
    cache = _make_cache()
    svc = DeviceService(api=MagicMock(), cache=cache)
    assert len(svc.list_all()) == 3


def test_list_by_room():
    cache = _make_cache()
    svc = DeviceService(api=MagicMock(), cache=cache)
    kitchen = svc.list_by_room("Кухня")
    assert len(kitchen) == 2
    assert all(d.id in ("d1", "d2") for d in kitchen)


def test_list_by_category():
    cache = _make_cache()
    svc = DeviceService(api=MagicMock(), cache=cache)
    lights = svc.list_by_category("bulb")
    assert len(lights) == 2


def test_has_feature():
    cache = _make_cache()
    svc = DeviceService(api=MagicMock(), cache=cache)
    assert svc.has_feature("d1", "on_off") is True
    assert svc.has_feature("d1", "nonexistent") is False
    assert svc.has_feature("nonexistent", "on_off") is False


@pytest.mark.asyncio
async def test_set_state():
    cache = _make_cache()
    api = AsyncMock()
    svc = DeviceService(api=api, cache=cache)
    attrs = [AttributeValueDto.of_bool("on_off", False)]
    await svc.set_state("d1", attrs)
    api.set_state.assert_called_once_with("d1", attrs)
    # Optimistic: desired patched
    dto = cache.get_device("d1")
    assert any(a.key == "on_off" and a.bool_value is False for a in dto.desired_state)


@pytest.mark.asyncio
async def test_turn_on():
    cache = _make_cache()
    api = AsyncMock()
    svc = DeviceService(api=api, cache=cache)
    await svc.turn_on("d1")
    api.set_state.assert_called_once()


@pytest.mark.asyncio
async def test_turn_off():
    cache = _make_cache()
    api = AsyncMock()
    svc = DeviceService(api=api, cache=cache)
    await svc.turn_off("d1")
    api.set_state.assert_called_once()
