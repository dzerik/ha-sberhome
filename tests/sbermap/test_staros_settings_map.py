"""Тесты маппинга настроек колонок Сбера → HA-сущности."""

from __future__ import annotations

from homeassistant.const import STATE_OFF, STATE_ON, EntityCategory, Platform

from custom_components.sberhome.aiosber.dto.settings import SettingScreenDto
from custom_components.sberhome.sbermap.transform.staros_settings import (
    build_staros_value,
    map_settings_screen_to_entities,
)

SERIAL = "SN123"
PRODUCT = "sberboom"


def _screen(nodes: list[dict]) -> SettingScreenDto:
    return SettingScreenDto.from_dict({"header": "h", "settings": nodes})


def _map(nodes: list[dict]):
    return map_settings_screen_to_entities(_screen(nodes), PRODUCT, SERIAL)


def test_toggle_maps_to_switch():
    ents = _map([{"id": "child", "type": "TOGGLE", "title": "Детский режим", "enabled": True}])
    assert len(ents) == 1
    ent = ents[0]
    assert ent.platform is Platform.SWITCH
    assert ent.state == STATE_ON
    assert ent.node_id == "child"
    assert ent.node_type == "TOGGLE"
    assert ent.serial == SERIAL
    assert ent.product == PRODUCT
    assert ent.name == "Детский режим"
    assert ent.entity_category is EntityCategory.CONFIG
    assert ent.unique_id == "staros_SN123_child"


def test_toggle_off_state():
    ents = _map([{"id": "n", "type": "UI_TOGGLE_SWITCHER", "enabled": False}])
    assert ents[0].platform is Platform.SWITCH
    assert ents[0].state == STATE_OFF


def test_radio_maps_to_select():
    ents = _map(
        [
            {
                "id": "theme",
                "type": "RADIO_BUTTONS",
                "title": "Тема",
                "checked": "dark",
                "radioButtons": [
                    {"title": "Тёмная", "value": "dark"},
                    {"title": "Светлая", "value": "light"},
                ],
            }
        ]
    )
    ent = ents[0]
    assert ent.platform is Platform.SELECT
    assert ent.options == ("dark", "light")
    assert ent.state == "dark"
    assert ent.option_titles == {"dark": "Тёмная", "light": "Светлая"}


def test_slider_maps_to_number():
    ents = _map(
        [
            {
                "id": "vol",
                "type": "SLIDER",
                "title": "Громкость",
                "value": 5,
                "min": 0,
                "max": 10,
                "step": 2,
                "unitSymbol": "%",
            }
        ]
    )
    ent = ents[0]
    assert ent.platform is Platform.NUMBER
    assert ent.state == 5
    assert ent.min_value == 0
    assert ent.max_value == 10
    assert ent.step == 2
    assert ent.unit == "%"


def test_slider_default_step():
    ents = _map([{"id": "v", "type": "STARCAST_VOLUME", "value": 1, "min": 0, "max": 3}])
    assert ents[0].platform is Platform.NUMBER
    assert ents[0].step == 1.0


def test_slider_range_from_min_max_step_array():
    # Диапазон приходит массивом minMaxStep, а не полями min/max/step.
    ents = _map([{"id": "vol", "type": "STARCAST_VOLUME", "value": 5, "minMaxStep": [0, 15, 1]}])
    ent = ents[0]
    assert ent.platform is Platform.NUMBER
    assert ent.min_value == 0
    assert ent.max_value == 15
    assert ent.step == 1


def test_duplicate_node_id_deduped():
    # Один node_id на корне и в раскрытом CARD → одна сущность (unique_id уникален).
    ents = _map(
        [
            {"id": "dup", "type": "TOGGLE", "enabled": True},
            {
                "id": "card",
                "type": "CARD",
                "action": "openScreen",
                "items": [{"id": "dup", "type": "TOGGLE", "enabled": False}],
            },
        ]
    )
    assert [e.node_id for e in ents] == ["dup"]


def test_recursion_into_children():
    ents = _map(
        [
            {
                "id": "card",
                "type": "CARD",
                "action": "openScreen",
                "items": [
                    {"id": "inner", "type": "TOGGLE", "enabled": True},
                    {"id": "hdr", "type": "SECTION_HEADER", "title": "Заголовок"},
                ],
            }
        ]
    )
    # CARD и SECTION_HEADER — декор (skip), но TOGGLE-ребёнок мапится.
    assert [e.node_id for e in ents] == ["inner"]
    assert ents[0].platform is Platform.SWITCH


def test_decor_skipped():
    ents = _map(
        [
            {"id": "h", "type": "HEADER_TEXT", "title": "текст"},
            {"type": "SECTION_HEADER", "title": "секция"},
            {"id": "c", "type": "COPY", "title": "ID", "value": "x"},
        ]
    )
    assert ents == []


def test_equalizer_expands_to_switch_select_and_bands():
    from custom_components.sberhome.sbermap.transform.staros_settings import Platform

    ents = _map(
        [
            {
                "id": "equalizer",
                "type": "EQUALIZER",
                "title": "Эквалайзер",
                "enabled": True,
                "activePreset": "user",
                "presets": ["flat", "user"],
                "frequencies": [60, 230, 910, 3600, 14000],
                "minMaxStep": [-6, 6, 1],
                "userPreset": {"presetName": "custom", "user": [3.5, 1.5, 0.0, -1.5, 2.5]},
            }
        ]
    )
    by_role = {e.eq_role: e for e in ents if e.eq_role in ("enabled", "preset")}
    bands = sorted((e for e in ents if e.eq_role == "band"), key=lambda e: e.eq_band_index)
    # enabled → switch
    assert by_role["enabled"].platform is Platform.SWITCH
    assert by_role["enabled"].state == STATE_ON
    assert by_role["enabled"].eq_group == "equalizer"
    # preset → select. Серверный activePreset="user" + кастомные полосы,
    # не совпавшие ни с одним пресетом → "Своя настройка".
    assert by_role["preset"].platform is Platform.SELECT
    assert by_role["preset"].state == "Своя настройка"
    # опции = серверные пресеты ∪ встроенные + «Своя настройка», без дублей
    opts = by_role["preset"].options
    assert opts[:2] == ("flat", "user")  # серверные — первыми
    assert "Басы" in opts and "Голос" in opts and "Эмбиент" in opts
    assert opts[-1] == "Своя настройка"
    # 5 полос → number с диапазоном из minMaxStep
    assert len(bands) == 5
    assert bands[0].platform is Platform.NUMBER
    assert bands[0].state == 3.5
    assert bands[0].min_value == -6 and bands[0].max_value == 6 and bands[0].step == 1
    # все сущности набора помечены общим eq_group и типом EQUALIZER
    assert all(e.eq_group == "equalizer" and e.node_type == "EQUALIZER" for e in ents)
    # unique_id уникальны
    assert len({e.unique_id for e in ents}) == len(ents)


def test_synthetic_equalizer_structure():
    """Синтетический эквалайзер: 5 полос @ известные частоты + пресеты."""
    from custom_components.sberhome.sbermap import (
        build_synthetic_equalizer,
        product_supports_equalizer,
    )

    assert product_supports_equalizer("sberboom-r2") is True
    assert product_supports_equalizer("sberbox-top") is False
    assert product_supports_equalizer(None) is False

    ents = build_synthetic_equalizer("sberboom-r2", "SN9")
    roles = {e.eq_role for e in ents}
    assert roles == {"enabled", "preset", "band"}
    bands = sorted(
        (e for e in ents if e.eq_role == "band"), key=lambda e: e.eq_band_index
    )
    assert [b.eq_frequency for b in bands] == [300, 500, 1400, 3900, 6500]
    assert all(b.min_value == -4 and b.max_value == 4 and b.step == 0.5 for b in bands)
    # встроенные пресеты доступны даже без серверных
    preset = next(e for e in ents if e.eq_role == "preset")
    assert "Басы" in preset.options and "Своя настройка" in preset.options


def test_synthetic_equalizer_carries_bands():
    """Переданные полосы/enabled переносятся в сущности."""
    from custom_components.sberhome.sbermap import build_synthetic_equalizer

    ents = build_synthetic_equalizer(
        "sberboom", "SN9", enabled=False, bands=[1.0, -2.0, 0.5, 0.0, 2.0]
    )
    bands = sorted(
        (e for e in ents if e.eq_role == "band"), key=lambda e: e.eq_band_index
    )
    assert [b.state for b in bands] == [1.0, -2.0, 0.5, 0.0, 2.0]
    enabled = next(e for e in ents if e.eq_role == "enabled")
    assert enabled.state == "off"


def test_fallback_bool_to_switch():
    ents = _map([{"id": "x", "type": "MYSTERY_FLAG", "enabled": False}])
    assert ents[0].platform is Platform.SWITCH
    assert ents[0].state == STATE_OFF


def test_fallback_options_to_select():
    ents = _map(
        [
            {
                "id": "x",
                "type": "MYSTERY_LIST",
                "checked": "a",
                "values": [{"title": "A", "value": "a"}, {"title": "B", "value": "b"}],
            }
        ]
    )
    assert ents[0].platform is Platform.SELECT
    assert ents[0].options == ("a", "b")


def test_fallback_number():
    ents = _map([{"id": "x", "type": "MYSTERY_NUM", "value": 3, "min": 0, "max": 5}])
    assert ents[0].platform is Platform.NUMBER
    assert ents[0].state == 3


def test_fallback_skip_when_no_signal():
    ents = _map([{"id": "x", "type": "MYSTERY", "title": "нечего показывать"}])
    assert ents == []


def test_node_without_id_or_type_skipped():
    ents = _map(
        [
            {"type": "TOGGLE", "enabled": True},
            {"id": "no_type", "enabled": True},
        ]
    )
    assert ents == []


def test_disabled_node_not_enabled_by_default():
    ents = _map([{"id": "n", "type": "TOGGLE", "enabled": True, "disabled": True}])
    assert ents[0].enabled_by_default is False


def test_enabled_by_default_true_when_not_disabled():
    ents = _map([{"id": "n", "type": "TOGGLE", "enabled": True}])
    assert ents[0].enabled_by_default is True


def test_build_staros_value():
    assert build_staros_value("TOGGLE", True) is True
    assert build_staros_value("UI_TOGGLE_SWITCHER", 1) is True
    assert build_staros_value("RADIO_BUTTONS", "dark") == "dark"
    assert build_staros_value("SELECT", 5) == "5"
    assert build_staros_value("SLIDER", 5.0) == 5
    assert isinstance(build_staros_value("SLIDER", 5.0), int)
    assert build_staros_value("STARCAST_VOLUME", 2.5) == 2.5
    # Неизвестный тип — passthrough.
    assert build_staros_value("MYSTERY", "raw") == "raw"
