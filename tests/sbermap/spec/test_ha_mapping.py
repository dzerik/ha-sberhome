"""Tests for sbermap.spec.ha_mapping — IMAGE_TYPE_MAP and resolve_category."""

from __future__ import annotations

import pytest

from custom_components.sberhome.sbermap.spec.ha_mapping import (
    CATEGORY_TO_HA_PLATFORMS,
    IMAGE_TYPE_MAP,
    resolve_category,
)


class TestResolveCategoryExactMatch:
    @pytest.mark.parametrize(
        "image_set_type,expected",
        [
            ("bulb_sber", "light"),
            ("ledstrip_sber", "led_strip"),
            ("dt_socket_sber", "socket"),
            ("relay", "relay"),
            ("cat_sensor_temp_humidity", "sensor_temp"),
            ("dt_sensor_water_leak", "sensor_water_leak"),
            ("cat_sensor_door", "sensor_door"),
            ("cat_sensor_motion", "sensor_pir"),
            ("scenario_button", "scenario_button"),
            ("curtain", "curtain"),
            ("hvac_ac", "hvac_ac"),
            ("hvac_underfloor", "hvac_underfloor_heating"),
            ("kettle", "kettle"),
            ("vacuum_cleaner", "vacuum_cleaner"),
            ("tv", "tv"),
            ("hub", "hub"),
            ("intercom", "intercom"),
        ],
    )
    def test_known_types_resolve(self, image_set_type, expected):
        assert resolve_category(image_set_type) == expected


class TestResolveCategorySubstring:
    """Substring-fallback для реальных Sber image_set_type вида 'XXX_bulb_sber_v2'."""

    def test_substring_matches_when_exact_misses(self):
        # "bulb_sber" — substring в "bulb_sber_v2"
        assert resolve_category("bulb_sber_v2") == "light"

    def test_prefix_substring(self):
        assert resolve_category("custom_curtain_pro") == "curtain"

    def test_long_specific_pattern_wins(self):
        # "cat_sensor_temp_humidity" — точное совпадение
        assert resolve_category("cat_sensor_temp_humidity") == "sensor_temp"


class TestResolveCategoryUnknown:
    def test_returns_none_for_unknown_image(self):
        assert resolve_category("brand_new_alien_device") is None

    def test_returns_none_for_empty_string(self):
        assert resolve_category("") is None

    def test_returns_none_for_none(self):
        assert resolve_category(None) is None


class TestResolveCategoryDtFormat:
    """Новый Sber формат `dt_<type>_<suffix>` (2025+).

    На проде видны `dt_bulb_e27_m`, `dt_bulb_e14` и т.п. Раньше они
    попадали в `resolve_category` → None, в панели `category: null`.
    """

    @pytest.mark.parametrize(
        "image_set_type,expected",
        [
            ("dt_bulb_e27_m", "light"),
            ("dt_bulb_e14", "light"),
            ("dt_led_strip_m", "led_strip"),
            ("dt_ledstrip_m", "led_strip"),
            ("dt_socket_1ch", "socket"),
            ("dt_relay_1ch", "relay"),
            ("dt_sensor_door_m", "sensor_door"),
            ("dt_sensor_motion_m", "sensor_pir"),
            ("dt_sensor_smoke_m", "sensor_smoke"),
            ("dt_sensor_gas_m", "sensor_gas"),
            ("dt_curtain_m", "curtain"),
            ("dt_valve_m", "valve"),
        ],
    )
    def test_dt_format_resolves(self, image_set_type, expected):
        assert resolve_category(image_set_type) == expected

    def test_generic_bulb_fallback(self):
        """`bulb` как подстрока — fallback для любых будущих вариаций."""
        assert resolve_category("smart_bulb_v2") == "light"

    @pytest.mark.parametrize(
        "image_set_type",
        ["cat_button_m", "cat_button_s", "cat_button_l"],
    )
    def test_virtual_cat_button_resolves_to_scenario_button(self, image_set_type):
        """`cat_button_*` — виртуальная c2c-кнопка (напр. Эмуляция присутствия).

        Сбер использует такой image_set_type для scenario-buttons, которые
        триггерят сценарии из мобильного приложения. Раньше они попадали
        в `resolve_category` → None и игнорировались.
        """
        assert resolve_category(image_set_type) == "scenario_button"


class TestImageTypeMapInvariants:
    def test_all_categories_in_platforms_map(self):
        """Все категории из IMAGE_TYPE_MAP должны иметь HA-platforms."""
        # Если категория есть — должно быть либо в CATEGORY_TO_HA_PLATFORMS,
        # либо это специальный (scenario_button — он в platforms map есть).
        for category in IMAGE_TYPE_MAP.values():
            assert category in CATEGORY_TO_HA_PLATFORMS, (
                f"Category {category!r} from IMAGE_TYPE_MAP missing in CATEGORY_TO_HA_PLATFORMS"
            )

    def test_no_duplicate_image_types(self):
        keys = list(IMAGE_TYPE_MAP.keys())
        assert len(keys) == len(set(keys))
