"""Тесты домена настроек колонок в координаторе."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, Platform

from custom_components.sberhome.aiosber.dto.settings import (
    SettingScreenDto,
    StarosDeviceDto,
)
from custom_components.sberhome.aiosber.exceptions import AuthError
from custom_components.sberhome.coordinator import SberHomeCoordinator, ThrottledPoll
from custom_components.sberhome.sbermap import StarosSettingEntity


def _screen() -> SettingScreenDto:
    return SettingScreenDto.from_dict(
        {
            "header": "Настройки",
            "settings": [
                {"id": "child", "type": "TOGGLE", "title": "Детский режим", "enabled": True},
                {"id": "vol", "type": "SLIDER", "value": 3, "min": 0, "max": 10},
            ],
        }
    )


def _coord(api) -> SberHomeCoordinator:
    coord = SberHomeCoordinator.__new__(SberHomeCoordinator)
    coord._staros_api = api
    coord.staros_settings_entities = {}
    coord.staros_devices = []
    coord._staros_poll = ThrottledPoll(3600, "StarosSettings")
    coord._staros_ws_trigger_at = None
    coord._staros_write_cooldown_until = 0.0
    coord.state_cache = MagicMock()
    coord.state_cache.get_all_devices = MagicMock(return_value={})
    coord.data = {}
    coord.async_set_updated_data = MagicMock()
    return coord


@pytest.mark.asyncio
async def test_maybe_poll_staros_populates_entities():
    api = AsyncMock()
    api.list_devices = AsyncMock(
        return_value=[
            StarosDeviceDto(device_id="d1", serial_number="SN1", product="sberboom", name="Колонка")
        ]
    )
    api.get_settings_deep = AsyncMock(return_value=_screen())
    coord = _coord(api)

    await coord._maybe_poll_staros()

    assert coord.staros_devices[0].serial_number == "SN1"
    ents = coord.staros_settings_entities["SN1"]
    # child(TOGGLE)→switch, vol(SLIDER)→number, плюс синтезированный эквалайзер
    # (product=sberboom поддерживает EQ, узла в дереве нет) → switch+select+5 полос.
    assert {e.platform for e in ents} == {
        Platform.SWITCH,
        Platform.NUMBER,
        Platform.SELECT,
    }
    eq = [e for e in ents if e.eq_group]
    assert len([e for e in eq if e.eq_role == "band"]) == 5


@pytest.mark.asyncio
async def test_staros_synthesizes_equalizer_when_absent():
    """Нет узла эквалайзера в дереве + поддерживаемый продукт → синтез."""
    api = AsyncMock()
    api.list_devices = AsyncMock(
        return_value=[StarosDeviceDto(device_id="d1", serial_number="SN1", product="sberboom-r2")]
    )
    api.get_settings_deep = AsyncMock(return_value=_screen())
    coord = _coord(api)

    await coord._refresh_staros()
    eq = [e for e in coord.staros_settings_entities["SN1"] if e.eq_group]
    assert len(eq) == 7  # enabled + preset + 5 полос
    assert any(e.eq_role == "preset" for e in eq)


@pytest.mark.asyncio
async def test_staros_no_synthesis_for_unsupported_product():
    """Неподдерживаемый продукт (sberbox) → эквалайзер не синтезируется."""
    api = AsyncMock()
    api.list_devices = AsyncMock(
        return_value=[StarosDeviceDto(device_id="d1", serial_number="SN1", product="sberbox")]
    )
    api.get_settings_deep = AsyncMock(return_value=_screen())
    coord = _coord(api)

    await coord._refresh_staros()
    assert not any(e.eq_group for e in coord.staros_settings_entities["SN1"])


@pytest.mark.asyncio
async def test_staros_synthesis_carries_bands_across_poll():
    """Полосы, выставленные ранее, переносятся при повторном синтезе."""
    api = AsyncMock()
    api.list_devices = AsyncMock(
        return_value=[StarosDeviceDto(device_id="d1", serial_number="SN1", product="sberboom-r2")]
    )
    api.get_settings_deep = AsyncMock(return_value=_screen())
    coord = _coord(api)
    await coord._refresh_staros()
    # эмулируем правку полосы №2 пользователем
    ents = coord.staros_settings_entities["SN1"]
    import dataclasses

    coord.staros_settings_entities["SN1"] = [
        dataclasses.replace(e, state=3.5) if e.node_id == "equalizer__band_2" else e for e in ents
    ]

    await coord._refresh_staros()
    band2 = next(
        e for e in coord.staros_settings_entities["SN1"] if e.node_id == "equalizer__band_2"
    )
    assert band2.state == 3.5


@pytest.mark.asyncio
async def test_async_refresh_staros_bypasses_throttle():
    """Форс-опрос перечитывает настройки даже когда троттл ещё не истёк."""
    import time as _time

    api = AsyncMock()
    api.list_devices = AsyncMock(
        return_value=[StarosDeviceDto(device_id="d1", serial_number="SN1", product="sberboom")]
    )
    api.get_settings_deep = AsyncMock(return_value=_screen())
    coord = _coord(api)
    # троттл «только что поллили» — обычный poll был бы пропущен
    coord._staros_poll.last_poll_at = _time.time()

    ok = await coord.async_refresh_staros()
    assert ok is True
    api.get_settings_deep.assert_awaited()  # опрос всё же выполнен
    assert "SN1" in coord.staros_settings_entities
    coord.async_set_updated_data.assert_called()


@pytest.mark.asyncio
async def test_async_refresh_staros_noop_when_api_none():
    coord = _coord(None)
    assert await coord.async_refresh_staros() is False


@pytest.mark.asyncio
async def test_async_refresh_staros_cooldown_blocks_auto_but_not_manual():
    """В окне cooldown авто-перечитка пропускается, ручная — выполняется."""
    import time as _time

    api = AsyncMock()
    api.list_devices = AsyncMock(
        return_value=[StarosDeviceDto(device_id="d1", serial_number="SN1", product="sberboom")]
    )
    api.get_settings_deep = AsyncMock(return_value=_screen())
    coord = _coord(api)
    coord._staros_write_cooldown_until = _time.time() + 30  # только что писали

    # авто-путь (respect_cooldown=True) — пропущен
    assert await coord.async_refresh_staros(respect_cooldown=True) is False
    api.get_settings_deep.assert_not_awaited()

    # ручной путь — игнорирует cooldown
    assert await coord.async_refresh_staros() is True
    api.get_settings_deep.assert_awaited()


@pytest.mark.asyncio
async def test_staros_write_sets_cooldown():
    """Запись настройки взводит cooldown (защита optimistic от затирания)."""
    import time as _time

    api = AsyncMock()
    api.set_setting = AsyncMock()
    coord = _coord(api)
    coord.staros_settings_entities = {
        "SN1": [
            StarosSettingEntity(
                platform=Platform.SWITCH,
                unique_id="staros_SN1_x",
                name="x",
                node_id="x",
                node_type="TOGGLE",
                product="sberboom",
                serial="SN1",
                state=STATE_OFF,
            )
        ]
    }
    before = _time.time()
    await coord.async_set_staros_setting("SN1", "sberboom", "x", "TOGGLE", True)
    assert coord._staros_write_cooldown_until > before


def test_ws_push_from_speaker_triggers_staros_refresh():
    """Gateway-WS push от колонки форсирует перечитку /v18 (throttled)."""
    api = AsyncMock()
    coord = _coord(api)
    coord.hass = MagicMock()
    scheduled: list = []
    coord.hass.async_create_task = lambda coro: scheduled.append(coro)

    dto = MagicMock()
    import unittest.mock as m

    with m.patch(
        "custom_components.sberhome.sbermap.resolve_device_category",
        return_value="sber_speaker",
    ):
        coord._maybe_trigger_staros_from_push(dto)
        # второй push сразу — задушен троттлом
        coord._maybe_trigger_staros_from_push(dto)

    # ровно один запланированный refresh (второй придушен)
    assert len(scheduled) == 1
    # закрываем корутину, чтобы не было RuntimeWarning
    scheduled[0].close()


def test_ws_push_from_non_speaker_no_trigger():
    """Push от обычного устройства не дёргает staros."""
    api = AsyncMock()
    coord = _coord(api)
    coord.hass = MagicMock()
    scheduled: list = []
    coord.hass.async_create_task = lambda coro: scheduled.append(coro)
    import unittest.mock as m

    dto = MagicMock()
    with m.patch(
        "custom_components.sberhome.sbermap.resolve_device_category", return_value="light"
    ):
        coord._maybe_trigger_staros_from_push(dto)
    assert scheduled == []


@pytest.mark.asyncio
async def test_maybe_poll_staros_gate_when_api_none():
    coord = _coord(None)
    # Не должно падать и ничего не трогает.
    await coord._maybe_poll_staros()
    assert coord.staros_settings_entities == {}


@pytest.mark.asyncio
async def test_maybe_poll_staros_auth_error_disables_domain():
    api = AsyncMock()
    api.list_devices = AsyncMock(side_effect=AuthError("no access"))
    coord = _coord(api)

    await coord._maybe_poll_staros()

    # AuthError гасит домен целиком.
    assert coord._staros_api is None
    assert coord.has_staros_settings() is False


@pytest.mark.asyncio
async def test_maybe_poll_staros_other_error_kept():
    api = AsyncMock()
    api.list_devices = AsyncMock(side_effect=RuntimeError("boom"))
    coord = _coord(api)

    await coord._maybe_poll_staros()

    # Прочая ошибка не гасит домен насовсем (best-effort).
    assert coord._staros_api is api


@pytest.mark.asyncio
async def test_set_staros_setting_optimistic():
    api = AsyncMock()
    api.set_setting = AsyncMock()
    coord = _coord(api)
    spec = StarosSettingEntity(
        platform=Platform.SWITCH,
        unique_id="staros_SN1_child",
        name="Детский режим",
        node_id="child",
        node_type="TOGGLE",
        product="sberboom",
        serial="SN1",
        state=STATE_OFF,
    )
    coord.staros_settings_entities = {"SN1": [spec]}

    await coord.async_set_staros_setting("SN1", "sberboom", "child", "TOGGLE", True)

    api.set_setting.assert_awaited_once_with("sberboom", "SN1", "child", "TOGGLE", True)
    assert coord.staros_settings_entities["SN1"][0].state == STATE_ON
    coord.async_set_updated_data.assert_called_once()


@pytest.mark.asyncio
async def test_set_staros_setting_gate_when_api_none():
    coord = _coord(None)
    coord.staros_settings_entities = {}
    # Без api команда — no-op, без исключений.
    await coord.async_set_staros_setting("SN1", "p", "n", "TOGGLE", True)
    coord.async_set_updated_data.assert_not_called()


def test_staros_speaker_present_by_settings_device():
    coord = _coord(None)
    coord.staros_devices = [StarosDeviceDto(serial_number="SN1", product="SberBoom")]
    assert coord.staros_speaker_present() is True


def test_staros_speaker_present_false_when_none():
    coord = _coord(None)
    assert coord.staros_speaker_present() is False


def _eq_group() -> list[StarosSettingEntity]:
    """Набор сущностей эквалайзера (enabled + preset + 3 полосы)."""
    base = {
        "node_type": "EQUALIZER",
        "product": "sberboom",
        "serial": "SN1",
        "eq_group": "equalizer",
    }
    return [
        StarosSettingEntity(
            platform=Platform.SWITCH,
            unique_id="staros_SN1_equalizer_enabled",
            name="Эквалайзер",
            node_id="equalizer__enabled",
            state=STATE_ON,
            eq_role="enabled",
            **base,
        ),
        StarosSettingEntity(
            platform=Platform.SELECT,
            unique_id="staros_SN1_equalizer_preset",
            name="пресет",
            node_id="equalizer__preset",
            state="user",
            options=("flat", "user"),
            eq_role="preset",
            **base,
        ),
        StarosSettingEntity(
            platform=Platform.NUMBER,
            unique_id="staros_SN1_equalizer_band_0",
            name="60",
            node_id="equalizer__band_0",
            state=1.0,
            eq_role="band",
            eq_band_index=0,
            **base,
        ),
        StarosSettingEntity(
            platform=Platform.NUMBER,
            unique_id="staros_SN1_equalizer_band_1",
            name="230",
            node_id="equalizer__band_1",
            state=2.0,
            eq_role="band",
            eq_band_index=1,
            **base,
        ),
        StarosSettingEntity(
            platform=Platform.NUMBER,
            unique_id="staros_SN1_equalizer_band_2",
            name="910",
            node_id="equalizer__band_2",
            state=3.0,
            eq_role="band",
            eq_band_index=2,
            **base,
        ),
    ]


@pytest.mark.asyncio
async def test_set_staros_equalizer_reconstructs_full_object():
    api = AsyncMock()
    api.set_setting = AsyncMock()
    coord = _coord(api)
    coord.staros_settings_entities = {"SN1": _eq_group()}

    # меняем полосу №2 на 4.0
    await coord.async_set_staros_setting("SN1", "sberboom", "equalizer__band_2", "EQUALIZER", 4.0)

    # set_setting вызван с id="equalizer", type="EQUALIZER" и ПОЛНЫМ объектом
    args = api.set_setting.await_args.args
    assert args[0] == "sberboom" and args[1] == "SN1"
    assert args[2] == "equalizer" and args[3] == "EQUALIZER"
    body = args[4]
    assert body["enabled"] is True
    assert body["activePreset"] == "user"
    assert body["user"] == [1.0, 2.0, 4.0]  # полоса 2 обновлена

    # optimistic: сущность полосы 2 обновилась
    band2 = next(
        e for e in coord.staros_settings_entities["SN1"] if e.node_id == "equalizer__band_2"
    )
    assert band2.state == 4.0


@pytest.mark.asyncio
async def test_set_staros_equalizer_toggle_enabled():
    api = AsyncMock()
    api.set_setting = AsyncMock()
    coord = _coord(api)
    coord.staros_settings_entities = {"SN1": _eq_group()}

    await coord.async_set_staros_setting(
        "SN1", "sberboom", "equalizer__enabled", "EQUALIZER", False
    )
    body = api.set_setting.await_args.args[4]
    assert body["enabled"] is False
    assert body["user"] == [1.0, 2.0, 3.0]  # полосы не тронуты


@pytest.mark.asyncio
async def test_set_staros_equalizer_preset_applies_bands():
    """Выбор встроенного пресета выставляет его полосы + activePreset=имя."""
    from custom_components.sberhome.sbermap import equalizer_preset_bands

    api = AsyncMock()
    api.set_setting = AsyncMock()
    coord = _coord(api)
    coord.staros_settings_entities = {"SN1": _eq_group()}

    await coord.async_set_staros_setting(
        "SN1", "sberboom", "equalizer__preset", "EQUALIZER", "Басы"
    )

    body = api.set_setting.await_args.args[4]
    rock = equalizer_preset_bands("Басы")
    # группа _eq_group имеет 3 полосы — применяются первые 3 значения пресета
    assert body["user"] == [rock[0], rock[1], rock[2]]
    assert body["activePreset"] == "Басы"

    # optimistic: полосы И селект обновились локально (не только селект)
    ents = {e.node_id: e for e in coord.staros_settings_entities["SN1"]}
    assert ents["equalizer__preset"].state == "Басы"
    assert ents["equalizer__band_0"].state == rock[0]
    assert ents["equalizer__band_1"].state == rock[1]
    assert ents["equalizer__band_2"].state == rock[2]


@pytest.mark.asyncio
async def test_set_staros_equalizer_manual_preset_maps_to_user():
    """Пресет «Своя настройка» уходит на сервер как activePreset="user"."""
    api = AsyncMock()
    api.set_setting = AsyncMock()
    coord = _coord(api)
    coord.staros_settings_entities = {"SN1": _eq_group()}

    await coord.async_set_staros_setting(
        "SN1", "sberboom", "equalizer__preset", "EQUALIZER", "Своя настройка"
    )
    body = api.set_setting.await_args.args[4]
    assert body["activePreset"] == "user"
    assert body["user"] == [1.0, 2.0, 3.0]  # полосы не тронуты
