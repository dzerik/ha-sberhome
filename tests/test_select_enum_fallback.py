"""Select platform — enum_values fallback из /devices/enums кэша.

Если sbermap-spec не задаёт `options` (Sber иногда отдаёт ENUM-атрибут
без enum_values inline), select.py должен достать список значений из
кэша `coordinator.enum_values_for(attribute_key)`. Это покрывает
кейс «голый ENUM», который раньше становился `_attr_options=[]` и
appeared as пустой dropdown в HA.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.const import Platform

from custom_components.sberhome.aiosber.dto import DeviceDto
from custom_components.sberhome.sbermap import HaEntityData
from custom_components.sberhome.select import SberSbermapSelect


def _make_coord(*, enums: dict[str, list[str]]) -> MagicMock:
    coord = MagicMock()
    coord.devices = {"dev-1": DeviceDto(id="dev-1")}
    coord.enum_values_for = MagicMock(side_effect=lambda key: list(enums.get(key, [])))
    return coord


def _entity(options: tuple[str, ...] | None) -> HaEntityData:
    return HaEntityData(
        platform=Platform.SELECT,
        unique_id="dev-1_hvac_work_mode",
        name="HVAC Mode",
        state="auto",
        state_attribute_key="hvac_work_mode",
        sber_category="hvac_ac",
        options=options,
    )


def test_select_uses_spec_options_when_available():
    """Spec задал options — fallback не дёргается."""
    coord = _make_coord(enums={"hvac_work_mode": ["auto", "cool"]})
    sel = SberSbermapSelect(coord, "dev-1", _entity(("auto", "heat")))
    assert sel._attr_options == ["auto", "heat"]
    coord.enum_values_for.assert_not_called()


def test_select_falls_back_to_enum_cache_when_options_missing():
    """Spec НЕ задал options — берём из coordinator.enum_values_for."""
    coord = _make_coord(enums={"hvac_work_mode": ["auto", "cool", "heat"]})
    sel = SberSbermapSelect(coord, "dev-1", _entity(None))
    assert sel._attr_options == ["auto", "cool", "heat"]
    coord.enum_values_for.assert_called_once_with("hvac_work_mode")


def test_select_falls_back_to_enum_cache_when_options_empty_tuple():
    """Empty tuple from spec тоже должен триггерить fallback."""
    coord = _make_coord(enums={"hvac_work_mode": ["auto"]})
    sel = SberSbermapSelect(coord, "dev-1", _entity(()))
    assert sel._attr_options == ["auto"]


def test_select_options_stay_empty_when_neither_spec_nor_cache_has_them():
    """Кэш тоже пустой — options=[]."""
    coord = _make_coord(enums={})
    sel = SberSbermapSelect(coord, "dev-1", _entity(None))
    assert sel._attr_options == []


def test_select_skips_fallback_when_state_key_missing():
    """Если spec не дал state_attribute_key, fallback не должен дёргать кэш."""
    coord = _make_coord(enums={"": ["x"]})
    ent = HaEntityData(
        platform=Platform.SELECT,
        unique_id="dev-1_unknown",
        name="X",
        state=None,
        sber_category="hvac_ac",
        options=None,
    )
    sel = SberSbermapSelect(coord, "dev-1", ent)
    assert sel._attr_options == []
    coord.enum_values_for.assert_not_called()
