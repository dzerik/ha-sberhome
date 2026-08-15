"""Тесты HA-сущностей настроек умных колонок Сбера."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory, Platform

from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.number import SberStarosSettingNumber
from custom_components.sberhome.sbermap import StarosSettingEntity
from custom_components.sberhome.select import SberStarosSettingSelect
from custom_components.sberhome.switch import SberStarosSettingSwitch


def _coord(spec: StarosSettingEntity) -> MagicMock:
    coord = MagicMock()
    coord.staros_settings_entities = {spec.serial: [spec]}
    coord.last_update_success = True
    coord.async_set_staros_setting = AsyncMock()
    return coord


def _switch_spec(state: str = STATE_ON) -> StarosSettingEntity:
    return StarosSettingEntity(
        platform=Platform.SWITCH,
        unique_id="staros_SN1_child",
        name="Детский режим",
        node_id="child",
        node_type="TOGGLE",
        product="sberboom",
        serial="SN1",
        state=state,
        entity_category=EntityCategory.CONFIG,
    )


def test_switch_reads_state_and_meta():
    spec = _switch_spec(STATE_ON)
    coord = _coord(spec)
    ent = SberStarosSettingSwitch(coord, spec)
    assert ent.unique_id == "staros_SN1_child"
    assert ent.name == "Детский режим"
    assert ent.is_on is True
    assert ent.available is True
    assert ent.entity_category is EntityCategory.CONFIG
    assert (DOMAIN, "SN1") in ent.device_info["identifiers"]
    # Не-эквалайзер настройка — без служебных eq-атрибутов
    assert ent.extra_state_attributes is None


def test_equalizer_band_exposes_eq_attributes():
    """Полоса эквалайзера отдаёт eq_group/eq_role/index/frequency для фронтенда."""
    spec = StarosSettingEntity(
        platform=Platform.NUMBER,
        unique_id="staros_SN1_equalizer_band_0",
        name="Эквалайзер 60 Гц",
        node_id="equalizer__band_0",
        node_type="EQUALIZER",
        product="sberboom",
        serial="SN1",
        state=1.5,
        eq_group="equalizer",
        eq_role="band",
        eq_band_index=0,
        eq_frequency=60,
    )
    coord = _coord(spec)
    ent = SberStarosSettingNumber(coord, spec)
    attrs = ent.extra_state_attributes
    assert attrs == {
        "eq_group": "equalizer",
        "eq_role": "band",
        "eq_band_index": 0,
        "eq_frequency": 60,
    }


def test_switch_off_and_unavailable_when_missing():
    spec = _switch_spec(STATE_OFF)
    coord = _coord(spec)
    ent = SberStarosSettingSwitch(coord, spec)
    assert ent.is_on is False
    # Дескриптор исчез из координатора → недоступна.
    coord.staros_settings_entities = {}
    assert ent.available is False
    assert ent.is_on is None


@pytest.mark.asyncio
async def test_switch_turn_on_off():
    spec = _switch_spec(STATE_OFF)
    coord = _coord(spec)
    ent = SberStarosSettingSwitch(coord, spec)
    await ent.async_turn_on()
    coord.async_set_staros_setting.assert_awaited_with("SN1", "sberboom", "child", "TOGGLE", True)
    await ent.async_turn_off()
    coord.async_set_staros_setting.assert_awaited_with("SN1", "sberboom", "child", "TOGGLE", False)


def test_select_options_and_current():
    spec = StarosSettingEntity(
        platform=Platform.SELECT,
        unique_id="staros_SN1_theme",
        name="Тема",
        node_id="theme",
        node_type="RADIO_BUTTONS",
        product="sberboom",
        serial="SN1",
        state="dark",
        options=("dark", "light"),
    )
    coord = _coord(spec)
    ent = SberStarosSettingSelect(coord, spec)
    assert ent.options == ["dark", "light"]
    assert ent.current_option == "dark"


@pytest.mark.asyncio
async def test_select_option_write():
    spec = StarosSettingEntity(
        platform=Platform.SELECT,
        unique_id="staros_SN1_theme",
        name="Тема",
        node_id="theme",
        node_type="RADIO_BUTTONS",
        product="sberboom",
        serial="SN1",
        state="dark",
        options=("dark", "light"),
    )
    coord = _coord(spec)
    ent = SberStarosSettingSelect(coord, spec)
    await ent.async_select_option("light")
    coord.async_set_staros_setting.assert_awaited_with(
        "SN1", "sberboom", "theme", "RADIO_BUTTONS", "light"
    )


def test_number_value_and_range():
    spec = StarosSettingEntity(
        platform=Platform.NUMBER,
        unique_id="staros_SN1_vol",
        name="Громкость",
        node_id="vol",
        node_type="SLIDER",
        product="sberboom",
        serial="SN1",
        state=4,
        min_value=0,
        max_value=10,
        step=2,
        unit="%",
    )
    coord = _coord(spec)
    ent = SberStarosSettingNumber(coord, spec)
    assert ent.native_value == 4.0
    assert ent.native_min_value == 0
    assert ent.native_max_value == 10
    assert ent.native_step == 2
    assert ent.native_unit_of_measurement == "%"


@pytest.mark.asyncio
async def test_number_set_value():
    spec = StarosSettingEntity(
        platform=Platform.NUMBER,
        unique_id="staros_SN1_vol",
        name="Громкость",
        node_id="vol",
        node_type="SLIDER",
        product="sberboom",
        serial="SN1",
        state=4,
        min_value=0,
        max_value=10,
    )
    coord = _coord(spec)
    ent = SberStarosSettingNumber(coord, spec)
    await ent.async_set_native_value(7)
    coord.async_set_staros_setting.assert_awaited_with("SN1", "sberboom", "vol", "SLIDER", 7)
