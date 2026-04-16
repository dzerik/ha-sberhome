"""Тесты GatewayCodec и C2cCodec — основное wire-format отличие."""

from __future__ import annotations

import pytest

from custom_components.sberhome.sbermap import (
    C2cCodec,
    CodecError,
    GatewayCodec,
    HsvColor,
    SberState,
    SberStateBundle,
    SberValue,
    ValueType,
)


# ====================================================================
# GatewayCodec
# ====================================================================
class TestGatewayValue:
    @pytest.fixture
    def codec(self):
        return GatewayCodec()

    def test_encode_bool(self, codec):
        out = codec.encode_value(SberValue.of_bool(True))
        assert out == {"type": "BOOL", "bool_value": True}

    def test_encode_integer_as_int(self, codec):
        """Gateway: INTEGER → int (НЕ string)."""
        out = codec.encode_value(SberValue.of_int(220))
        assert out == {"type": "INTEGER", "integer_value": 220}
        assert isinstance(out["integer_value"], int)

    def test_encode_color_uses_full_names(self, codec):
        """Gateway: hue/saturation/brightness, type=COLOR."""
        out = codec.encode_value(SberValue.of_color(HsvColor(180, 80, 90)))
        assert out == {
            "type": "COLOR",
            "color_value": {"hue": 180, "saturation": 80, "brightness": 90},
        }

    def test_decode_bool(self, codec):
        v = codec.decode_value({"type": "BOOL", "bool_value": False})
        assert v.type is ValueType.BOOL
        assert v.bool_value is False

    def test_decode_color(self, codec):
        v = codec.decode_value({
            "type": "COLOR",
            "color_value": {"hue": 200, "saturation": 80, "brightness": 70},
        })
        assert v.type is ValueType.COLOR
        assert v.color_value == HsvColor(200, 80, 70)

    def test_decode_unknown_type_raises(self, codec):
        with pytest.raises(CodecError, match="unknown wire type"):
            codec.decode_value({"type": "PURPLE", "value": 1})

    def test_decode_missing_type_raises(self, codec):
        with pytest.raises(CodecError, match="missing 'type'"):
            codec.decode_value({"bool_value": True})

    def test_color_roundtrip(self, codec):
        original = SberValue.of_color(HsvColor(120, 60, 80))
        roundtrip = codec.decode_value(codec.encode_value(original))
        assert roundtrip == original


class TestGatewayState:
    def test_encode_state_flat(self):
        c = GatewayCodec()
        s = SberState("on_off", SberValue.of_bool(True))
        # Gateway: flat (key + value fields на одном уровне)
        assert c.encode_state(s) == {"key": "on_off", "type": "BOOL", "bool_value": True}

    def test_decode_state(self):
        c = GatewayCodec()
        s = c.decode_state({"key": "x", "type": "INTEGER", "integer_value": 42})
        assert s.key == "x"
        assert s.value.integer_value == 42

    def test_bundle_roundtrip(self):
        c = GatewayCodec()
        bundle = SberStateBundle(
            device_id="d1",
            states=(
                SberState("on_off", SberValue.of_bool(True)),
                SberState("brightness", SberValue.of_int(500)),
            ),
        )
        encoded = c.encode_bundle(bundle, direction="desired")
        assert encoded["device_id"] == "d1"
        assert "desired_state" in encoded
        roundtrip = c.decode_bundle(encoded)
        assert roundtrip.value_of("on_off") is True
        assert roundtrip.value_of("brightness") == 500


# ====================================================================
# C2cCodec — критические отличия от Gateway
# ====================================================================
class TestC2cValue:
    @pytest.fixture
    def codec(self):
        return C2cCodec()

    def test_encode_integer_as_string(self, codec):
        """C2C: INTEGER → string '220' (КРИТИЧЕСКОЕ отличие от Gateway)."""
        out = codec.encode_value(SberValue.of_int(220))
        assert out == {"type": "INTEGER", "integer_value": "220"}
        assert isinstance(out["integer_value"], str)

    def test_encode_color_uses_short_names_with_u(self, codec):
        """C2C: h/s/v короткие, type=COLOUR с u."""
        out = codec.encode_value(SberValue.of_color(HsvColor(180, 80, 90)))
        assert out["type"] == "COLOUR"  # British
        assert "colour_value" in out
        assert "color_value" not in out
        # Saturation/brightness ×10
        assert out["colour_value"] == {"h": 180, "s": 800, "v": 900}

    def test_color_brightness_min_100_per_vr_004(self, codec):
        """C2C VR-004: brightness wire-min = 100 (если 0 — устройство rejected)."""
        out = codec.encode_value(SberValue.of_color(HsvColor(0, 0, 0)))
        assert out["colour_value"]["v"] == 100

    def test_decode_integer_from_string(self, codec):
        v = codec.decode_value({"type": "INTEGER", "integer_value": "220"})
        assert v.integer_value == 220
        assert isinstance(v.integer_value, int)

    def test_decode_colour_to_canonical(self, codec):
        v = codec.decode_value({
            "type": "COLOUR",
            "colour_value": {"h": 180, "s": 800, "v": 900},
        })
        assert v.type is ValueType.COLOR
        # 800/10 = 80, 900/10 = 90
        assert v.color_value == HsvColor(180, 80, 90)


class TestC2cState:
    def test_encode_state_nested_value(self):
        """C2C: value вложенный, не flat (отличие от Gateway)."""
        c = C2cCodec()
        s = SberState("on_off", SberValue.of_bool(True))
        assert c.encode_state(s) == {
            "key": "on_off",
            "value": {"type": "BOOL", "bool_value": True},
        }

    def test_decode_state_from_nested(self):
        c = C2cCodec()
        raw = {"key": "on_off", "value": {"type": "BOOL", "bool_value": True}}
        assert c.decode_state(raw).value.bool_value is True

    def test_decode_state_missing_value_raises(self):
        c = C2cCodec()
        with pytest.raises(CodecError, match="missing 'value' dict"):
            c.decode_state({"key": "on_off"})

    def test_bundle_uses_states_field(self):
        c = C2cCodec()
        bundle = SberStateBundle(
            device_id="d", states=(SberState("on_off", SberValue.of_bool(True)),)
        )
        out = c.encode_bundle(bundle)
        assert "states" in out
        assert "desired_state" not in out


# ====================================================================
# Cross-codec wire divergence (как защита от accidental drift)
# ====================================================================
class TestCodecDivergence:
    def test_color_field_names_differ(self):
        """Gateway уse color_value, C2C — colour_value (с u)."""
        v = SberValue.of_color(HsvColor(180, 80, 90))
        g_out = GatewayCodec().encode_value(v)
        c_out = C2cCodec().encode_value(v)
        assert "color_value" in g_out and "color_value" not in c_out
        assert "colour_value" in c_out and "colour_value" not in g_out

    def test_color_type_strings_differ(self):
        v = SberValue.of_color(HsvColor(180, 80, 90))
        assert GatewayCodec().encode_value(v)["type"] == "COLOR"
        assert C2cCodec().encode_value(v)["type"] == "COLOUR"

    def test_integer_serialization_differs(self):
        v = SberValue.of_int(100)
        assert isinstance(GatewayCodec().encode_value(v)["integer_value"], int)
        assert isinstance(C2cCodec().encode_value(v)["integer_value"], str)

    def test_state_structure_differs(self):
        s = SberState("k", SberValue.of_bool(True))
        g = GatewayCodec().encode_state(s)
        c = C2cCodec().encode_state(s)
        # Gateway flat
        assert "type" in g and "bool_value" in g
        # C2C nested
        assert "value" in c and "type" in c["value"]
