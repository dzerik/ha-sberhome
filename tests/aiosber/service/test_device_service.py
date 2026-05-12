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


# ---------------------------------------------------------------------------
# refresh() — multi-home aware через 4 параллельных flat-list запроса
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_uses_flat_endpoints(monkeypatch):
    """refresh() должен делать 4 параллельных запроса вместо /tree."""
    cache = StateCache()
    api = MagicMock()
    api._transport = MagicMock()
    api.list_flat = AsyncMock(
        return_value=[
            DeviceDto(id="d1", group_ids=["r-kitchen"]),
            DeviceDto(id="d2", group_ids=["h-main"]),
        ]
    )

    # GroupAPI замокаем через monkeypatch — нам нужны разные list-вызовы
    # с group_type=HOME/ROOM/GROUP. Возвращаем по списку для каждого.
    async def fake_list(self, *, group_type=None, limit=1000):
        if group_type == "HOME":
            return [UnionDto(id="h-main", name="Мой дом", group_type=UnionType.HOME)]
        if group_type == "ROOM":
            return [
                UnionDto(
                    id="r-kitchen",
                    name="Кухня",
                    group_type=UnionType.ROOM,
                    parent_id="h-main",
                )
            ]
        return []  # GROUP

    from custom_components.sberhome.aiosber.api.groups import GroupAPI

    monkeypatch.setattr(GroupAPI, "list", fake_list)

    svc = DeviceService(api=api, cache=cache)
    await svc.refresh()

    # Cache теперь должен содержать оба device, с home/room mappings.
    assert len(cache.get_all_devices()) == 2
    assert cache.device_home_id("d1") == "h-main"
    assert cache.device_room_id("d1") == "r-kitchen"
    assert cache.device_home_id("d2") == "h-main"
    assert cache.device_room_id("d2") is None  # top-level
    api.list_flat.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_falls_back_to_tree_on_error(monkeypatch):
    """Если flat-API упал — fallback на /device_groups/tree (legacy)."""
    cache = StateCache()
    api = MagicMock()
    api._transport = MagicMock()
    api.list_flat = AsyncMock(side_effect=RuntimeError("boom"))

    from custom_components.sberhome.aiosber.api.groups import GroupAPI

    async def fake_list(self, *, group_type=None, limit=1000):
        return []

    monkeypatch.setattr(GroupAPI, "list", fake_list)

    # Симулируем tree-response через mock transport.
    tree_resp = MagicMock()
    tree_resp.json = MagicMock(
        return_value={
            "result": {
                "group": {"id": "h-legacy", "name": "Legacy", "group_type": "HOME"},
                "devices": [],
                "children": [],
            }
        }
    )
    api._transport.get = AsyncMock(return_value=tree_resp)

    svc = DeviceService(api=api, cache=cache)
    await svc.refresh()

    # Tree-fallback заполнил cache.
    homes = cache.get_homes()
    assert len(homes) == 1
    assert homes[0].id == "h-legacy"
    api._transport.get.assert_awaited()
