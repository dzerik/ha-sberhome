"""Тесты canonical value types — HsvColor / SberValue / Bundle."""

from __future__ import annotations

from custom_components.sberhome.sbermap import (
    HsvColor,
    SberState,
    SberStateBundle,
    SberValue,
    ValueType,
)


# ============== HsvColor ==============
class TestHsvColor:
    def test_basic(self):
        c = HsvColor(180, 80, 90)
        assert c.hue == 180
        assert c.saturation == 80
        assert c.brightness == 90

    def test_clamping(self):
        """Out-of-range values clamped в свои диапазоны."""
        c = HsvColor(400, 200, -10)
        assert c.hue == 359
        assert c.saturation == 100
        assert c.brightness == 0

    def test_to_ha_brightness_scaling(self):
        # 100% → 255
        assert HsvColor(0, 0, 100).to_ha_brightness() == 255
        # 50% → ~128
        assert HsvColor(0, 0, 50).to_ha_brightness() == 128
        # 0% → 0
        assert HsvColor(0, 0, 0).to_ha_brightness() == 0

    def test_to_ha_hs_returns_floats(self):
        c = HsvColor(180, 80, 90)
        assert c.to_ha_hs() == (180.0, 80.0)

    def test_from_ha(self):
        c = HsvColor.from_ha(180.7, 49.5, brightness=128)
        assert c.hue == 181
        assert c.saturation == 50
        # brightness 128 / 255 ≈ 50%
        assert 49 <= c.brightness <= 51


# ============== SberValue ==============
class TestSberValue:
    def test_of_bool(self):
        v = SberValue.of_bool(True)
        assert v.type is ValueType.BOOL
        assert v.value is True

    def test_of_int_ensures_int_type(self):
        v = SberValue.of_int(500)
        assert v.type is ValueType.INTEGER
        assert v.integer_value == 500

    def test_of_color(self):
        c = HsvColor(120, 100, 80)
        v = SberValue.of_color(c)
        assert v.type is ValueType.COLOR
        assert v.color_value == c
        assert v.value == c

    def test_value_returns_correct_field_per_type(self):
        cases = [
            (SberValue.of_bool(False), False),
            (SberValue.of_int(42), 42),
            (SberValue.of_float(3.14), 3.14),
            (SberValue.of_string("hi"), "hi"),
            (SberValue.of_enum("auto"), "auto"),
        ]
        for v, expected in cases:
            assert v.value == expected


# ============== SberStateBundle ==============
class TestStateBundle:
    def test_get_existing(self):
        b = SberStateBundle(
            device_id="x",
            states=(
                SberState("on_off", SberValue.of_bool(True)),
                SberState("brightness", SberValue.of_int(500)),
            ),
        )
        assert b.value_of("on_off") is True
        assert b.value_of("brightness") == 500

    def test_get_missing_returns_none(self):
        b = SberStateBundle(device_id="x", states=())
        assert b.value_of("on_off") is None

    def test_get_returns_value_object(self):
        b = SberStateBundle(
            device_id="x",
            states=(SberState("on_off", SberValue.of_bool(True)),),
        )
        v = b.get("on_off")
        assert v is not None
        assert v.type is ValueType.BOOL
