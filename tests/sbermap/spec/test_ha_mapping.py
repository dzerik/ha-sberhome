"""Tests for sbermap.spec.ha_mapping — IMAGE_TYPE_MAP and resolve_category."""

from __future__ import annotations

import pytest

from custom_components.sberhome.sbermap.spec.ha_mapping import (
    CATEGORY_TO_HA_PLATFORMS,
    IMAGE_TYPE_MAP,
    resolve_category,
    resolve_device_category,
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
        ["cat_ledstrip_m", "cat_ledstrip_s", "cat_ledstrip_l", "cat_ledstrip"],
    )
    def test_cat_ledstrip_variants_resolve_to_led_strip(self, image_set_type):
        """`cat_ledstrip_*` — формат image_set_type для умной ленты Sber (SBDV-00055).

        Покрывается token-fallback'ом (token `ledstrip` ∈ CATEGORY_KEYWORDS).
        Раньше попадал в `resolve_category` → None, устройство игнорировалось
        с сообщением "категория не распознаётся". См. issue #1.
        """
        assert resolve_category(image_set_type) == "led_strip"

    @pytest.mark.parametrize(
        "image_set_type",
        ["cat_light_m", "cat_light_s", "cat_light_l", "cat_light_basic", "cat_light"],
    )
    def test_cat_light_variants_resolve_to_light(self, image_set_type):
        """`cat_light_*` — формат image_set_type для умных ламп Sber.

        Артефакт `cat_light_basic` встречается в payload'ах diagnose-тестов
        — реальный пример из API. Покрывается token-fallback'ом (`light` ∈
        CATEGORY_KEYWORDS["light"]).
        """
        assert resolve_category(image_set_type) == "light"

    @pytest.mark.parametrize(
        "image_set_type",
        ["cat_vacuum_m", "cat_vacuum_s", "cat_vacuum"],
    )
    def test_cat_vacuum_variants_resolve_to_vacuum_cleaner(self, image_set_type):
        """`cat_vacuum_*` — гипотетический формат для роботов-пылесосов Sber.

        Покрывается token-fallback'ом (token `vacuum` ∈ CATEGORY_KEYWORDS).
        """
        assert resolve_category(image_set_type) == "vacuum_cleaner"

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

    @pytest.mark.parametrize(
        "image_set_type",
        [
            "dt_boom_r2_dark_blue_s",
            "dt_boom_mini",
            "dt_portal_v2",
            "dt_box_top",
            "dt_satellite_2024",
        ],
    )
    def test_sber_speaker_variants_resolve(self, image_set_type):
        """SberBoom/Portal/Box/Satellite → category sber_speaker."""
        assert resolve_category(image_set_type) == "sber_speaker"


class TestResolveCategoryTokenFallback:
    """Token-fallback (level 3): автоматическое покрытие любых новых префиксов.

    `IMAGE_TYPE_MAP` не нужно расширять для каждого нового `xyz_*` или
    `cat_*` формата — slug разбивается на токены и сматчится по
    `CATEGORY_KEYWORDS`.
    """

    @pytest.mark.parametrize(
        "image_set_type,expected",
        [
            # Light variations
            ("xyz_bulb_pro_2026", "light"),
            ("smart_light_basic", "light"),
            ("cat_light_basic", "light"),
            # LED strip variations
            ("xyz_ledstrip_pro_2026", "led_strip"),
            ("new_led_strip_v3", "led_strip"),
            # Vacuum
            ("brand_vacuum_pro", "vacuum_cleaner"),
            # Multi-token phrase priority — sensor_temp_humidity побеждает
            # sensor (если бы был short keyword).
            ("xyz_sensor_temp_humidity_v2", "sensor_temp"),
            ("xyz_sensor_water_leak_v2", "sensor_water_leak"),
            # HVAC composite
            ("xyz_hvac_underfloor_heating_v2", "hvac_underfloor_heating"),
            # Sber speakers — boom/portal/satellite tokens
            ("new_boom_2026", "sber_speaker"),
            ("custom_portal_v3", "sber_speaker"),
        ],
    )
    def test_token_fallback_resolves(self, image_set_type, expected):
        assert resolve_category(image_set_type) == expected

    def test_token_fallback_returns_none_for_no_keyword(self):
        """Slug без known keyword'ов → None."""
        assert resolve_category("xyz_unknown_alien_device_v9") is None

    def test_long_phrase_priority(self):
        """Длинный multi-token window побеждает короткий single-token.

        `sensor_temp_humidity` (3 токена) → sensor_temp,
        а не `sensor` (если бы был такой keyword).
        """
        assert resolve_category("xyz_sensor_temp_humidity") == "sensor_temp"


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


class TestSlugFirstResolution:
    """resolve_category(slug=...) — приоритет 0 (выше image_set_type)."""

    def test_known_slug_wins_over_image_set_type(self):
        """Slug из Sber API — единственный источник истины при exact match."""
        assert resolve_category("xyz_unknown", slug="valve") == "valve"

    def test_known_slug_works_when_image_set_type_empty(self):
        """Колонкам Sber приходит slug=default + image_set_type — slug=default
        не валидный, но slug=hvac_fan валидный без помощи image_set_type."""
        assert resolve_category(None, slug="hvac_fan") == "hvac_fan"
        assert resolve_category("", slug="led_strip") == "led_strip"

    def test_unknown_slug_falls_back_to_image_set_type(self):
        """`slug="default"` (SberBoom Home) — не в CATEGORY_TO_HA_PLATFORMS,
        идём в fallback по image_set_type."""
        # SberBoom Home: full_categories=[{"slug":"default"}], но
        # image_set_type=dt_boom_r2_dark_blue_s → substring → sber_speaker.
        assert resolve_category("dt_boom_r2_dark_blue_s", slug="default") == "sber_speaker"

    def test_slug_none_uses_image_set_type(self):
        """slug=None → классическая логика по image_set_type."""
        assert resolve_category("bulb_sber", slug=None) == "light"

    def test_invalid_slug_does_not_break_resolution(self):
        """Неизвестный slug не блокирует image_set_type fallback."""
        assert resolve_category("dt_curtain", slug="some_future_category") == "curtain"


class TestResolveDeviceCategory:
    """resolve_device_category(dto) — удобная обёртка для DeviceDto."""

    def test_dto_with_slug_uses_slug_first(self):
        """Если у DTO есть primary_category_slug — используется он."""

        class FakeDto:
            image_set_type = "dt_unknown_xyz"
            primary_category_slug = "valve"

        assert resolve_device_category(FakeDto()) == "valve"

    def test_dto_without_slug_uses_image_set_type(self):
        """primary_category_slug=None → fallback на image_set_type."""

        class FakeDto:
            image_set_type = "cat_valve_l"
            primary_category_slug = None

        assert resolve_device_category(FakeDto()) == "valve"

    def test_dto_with_default_slug_uses_image_set_type(self):
        """slug=default (колонки Sber) — fallback на image_set_type."""

        class FakeDto:
            image_set_type = "dt_boom_r2_dark_blue_s"
            primary_category_slug = "default"

        assert resolve_device_category(FakeDto()) == "sber_speaker"

    def test_dto_missing_both_returns_none(self):
        """Совсем нет данных — None."""

        class FakeDto:
            image_set_type = None
            primary_category_slug = None

        assert resolve_device_category(FakeDto()) is None
