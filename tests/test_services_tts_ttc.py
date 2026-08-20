"""Tests для sberhome.tts_send / ttc_send — роутинг device→home.

Главное, что проверяем: `device_ids` уходят ТОЛЬКО в дом-владелец колонки
(а не broadcast'ом во все дома, как было в исходном PR #48). Без `device_ids`
— broadcast на все дома. TTC использует ttc_service, TTS — tts_service.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome import _async_register_services


def _make_hass(coord: MagicMock) -> MagicMock:
    hass = MagicMock()
    hass.data = {}
    hass.services.async_register = MagicMock()
    entry = MagicMock()
    entry.runtime_data = coord
    hass.config_entries.async_loaded_entries.return_value = [entry]
    return hass


def _handlers(hass: MagicMock) -> dict[str, object]:
    """Регистрирует сервисы и возвращает {name: handler} из mock-вызовов."""
    _async_register_services(hass)
    out: dict[str, object] = {}
    for call in hass.services.async_register.call_args_list:
        # async_register(DOMAIN, name, handler, schema=..., supports_response=...)
        out[call.args[1]] = call.args[2]
    return out


def _coord_two_homes() -> MagicMock:
    coord = MagicMock()
    coord.tts_service.send = AsyncMock()
    coord.ttc_service.send = AsyncMock()
    home1, home2 = MagicMock(), MagicMock()
    home1.id, home2.id = "H1", "H2"
    coord.state_cache.get_homes.return_value = [home1, home2]
    mapping = {"dA": "H1", "dB": "H2"}
    coord.state_cache.device_home_id.side_effect = lambda did: mapping.get(did)
    return coord


def _call(**data: object) -> MagicMock:
    call = MagicMock()
    call.data = data
    return call


@pytest.mark.asyncio
async def test_tts_send_routes_device_to_owning_home_only():
    coord = _coord_two_homes()
    tts_send = _handlers(_make_hass(coord))["tts_send"]

    res = await tts_send(_call(message="hi", device_ids=["dA"]))

    coord.tts_service.send.assert_awaited_once_with("H1", "hi", ["dA"])
    assert res["ok"] is True
    assert res["results"] == {"H1": "ok"}


@pytest.mark.asyncio
async def test_tts_send_groups_multiple_devices_by_home():
    coord = _coord_two_homes()
    tts_send = _handlers(_make_hass(coord))["tts_send"]

    await tts_send(_call(message="hi", device_ids=["dA", "dB"]))

    routed = {c.args[0]: c.args[2] for c in coord.tts_service.send.await_args_list}
    assert routed == {"H1": ["dA"], "H2": ["dB"]}


@pytest.mark.asyncio
async def test_tts_send_broadcast_when_no_device_ids():
    coord = _coord_two_homes()
    tts_send = _handlers(_make_hass(coord))["tts_send"]

    await tts_send(_call(message="hi"))

    routed = {c.args[0]: c.args[2] for c in coord.tts_service.send.await_args_list}
    assert routed == {"H1": None, "H2": None}


@pytest.mark.asyncio
async def test_tts_send_unknown_device_sends_nothing():
    coord = _coord_two_homes()
    tts_send = _handlers(_make_hass(coord))["tts_send"]

    res = await tts_send(_call(message="hi", device_ids=["zzz"]))

    coord.tts_service.send.assert_not_awaited()
    assert res["ok"] is False


@pytest.mark.asyncio
async def test_ttc_send_uses_ttc_service_and_routes():
    coord = _coord_two_homes()
    ttc_send = _handlers(_make_hass(coord))["ttc_send"]

    await ttc_send(_call(message="анекдот", device_ids=["dB"]))

    coord.ttc_service.send.assert_awaited_once_with("H2", "анекдот", ["dB"])
    coord.tts_service.send.assert_not_awaited()
