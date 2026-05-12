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


def _make_devices_resp(devices: list[dict]) -> MagicMock:
    """Mock httpx.Response с `result: [devices]` payload."""
    r = MagicMock()
    r.json = MagicMock(return_value={"result": devices})
    return r


@pytest.mark.asyncio
async def test_refresh_uses_flat_endpoints(monkeypatch):
    """refresh() делает 4 параллельных запроса + naполняет raw payloads."""
    cache = StateCache()
    api = MagicMock()
    api._transport = MagicMock()

    # /devices?pagination — raw payloads с device_info чтобы DeviceDto.from_dict
    # успешно их распарсил.
    raw_d1 = {
        "id": "d1",
        "name": {"name": "Лампа"},
        "device_info": {"manufacturer": "Sber", "model": "X"},
        "group_ids": ["r-kitchen"],
    }
    raw_d2 = {
        "id": "d2",
        "name": {"name": "Boom"},
        "device_info": {"manufacturer": "Sber", "model": "Y"},
        "group_ids": ["h-main"],
    }
    # /devices/enums — best-effort.
    enums_resp = MagicMock()
    enums_resp.json = MagicMock(return_value={"result": {"hvac_work_mode": ["cool", "heat"]}})

    async def fake_transport_get(path, params=None, **kwargs):
        if path == "/devices":
            return _make_devices_resp([raw_d1, raw_d2])
        if path == "/devices/enums":
            return enums_resp
        raise AssertionError(f"unexpected GET: {path}")

    api._transport.get = AsyncMock(side_effect=fake_transport_get)

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
    # Расширенный enums() — нормализованный возврат.
    api.enums = AsyncMock(return_value={"hvac_work_mode": ["cool", "heat"]})

    svc = DeviceService(api=api, cache=cache)
    await svc.refresh()

    # Devices + связи в state.
    assert len(cache.get_all_devices()) == 2
    assert cache.device_home_id("d1") == "h-main"
    assert cache.device_room_id("d1") == "r-kitchen"
    assert cache.device_home_id("d2") == "h-main"
    assert cache.device_room_id("d2") is None  # top-level

    # Raw payloads сохранены — UI/diagnostics могут их получить.
    assert cache.get_raw_payload("d1") == raw_d1
    assert cache.get_raw_payload("d2") == raw_d2

    # Enums best-effort подтянулись.
    assert cache.get_enum_values("hvac_work_mode") == ["cool", "heat"]


@pytest.mark.asyncio
async def test_refresh_falls_back_to_tree_on_error(monkeypatch):
    """Если flat-API упал — fallback на /device_groups/tree (legacy)."""
    cache = StateCache()
    api = MagicMock()
    api._transport = MagicMock()

    async def fake_list(self, *, group_type=None, limit=1000):
        return []

    monkeypatch.setattr("custom_components.sberhome.aiosber.api.groups.GroupAPI.list", fake_list)

    # Tree-fallback ответ.
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

    async def fake_transport_get(path, params=None, **kwargs):
        if path == "/devices":
            raise RuntimeError("boom — flat-API упал")
        if path == "/device_groups/tree":
            return tree_resp
        raise AssertionError(f"unexpected GET: {path}")

    api._transport.get = AsyncMock(side_effect=fake_transport_get)

    svc = DeviceService(api=api, cache=cache)
    await svc.refresh()

    # Tree-fallback заполнил cache.
    homes = cache.get_homes()
    assert len(homes) == 1
    assert homes[0].id == "h-legacy"


@pytest.mark.asyncio
async def test_refresh_enums_fetch_failure_does_not_break_refresh(monkeypatch):
    """Если /devices/enums падает — refresh всё равно успешен (best-effort)."""
    cache = StateCache()
    api = MagicMock()
    api._transport = MagicMock()

    async def fake_transport_get(path, params=None, **kwargs):
        if path == "/devices":
            return _make_devices_resp([])
        if path == "/devices/enums":
            raise RuntimeError("enums endpoint dead")
        raise AssertionError(f"unexpected GET: {path}")

    api._transport.get = AsyncMock(side_effect=fake_transport_get)
    api.enums = AsyncMock(side_effect=RuntimeError("enums endpoint dead"))

    async def fake_list(self, *, group_type=None, limit=1000):
        return []

    monkeypatch.setattr("custom_components.sberhome.aiosber.api.groups.GroupAPI.list", fake_list)

    svc = DeviceService(api=api, cache=cache)
    # Не должно бросить — enums-failure не валит refresh.
    await svc.refresh()
    assert cache.get_enums() == {}
