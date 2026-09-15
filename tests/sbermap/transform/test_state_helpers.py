"""Чтение состояния штор, обратный маппинг режимов климата и реестр FeatureSpec."""

from __future__ import annotations

import pytest
from homeassistant.components.climate import HVACMode
from homeassistant.components.cover import CoverState

from custom_components.sberhome.aiosber.dto import DeviceDto
from custom_components.sberhome.sbermap import cover_state_from_dto, map_hvac_mode_to_sber
from custom_components.sberhome.sbermap.transform.feature_specs import (
    FEATURE_SPECS,
    feature_spec_for,
)


def _curtain(reported: list[dict]) -> DeviceDto:
    dto = DeviceDto.from_dict(
        {"id": "curtain-1", "image_set_type": "cat_curtain", "reported_state": reported}
    )
    assert dto is not None
    return dto


@pytest.mark.parametrize(
    ("open_state", "expected"),
    [
        ("opened", CoverState.OPEN),
        ("close", CoverState.CLOSED),
        ("opening", CoverState.OPENING),
        ("closing", CoverState.CLOSING),
        ("jammed", CoverState.CLOSED),
    ],
)
def test_cover_state_from_dto_maps_open_state(open_state, expected):
    snapshot = cover_state_from_dto(
        _curtain(
            [
                {"key": "open_state", "type": "ENUM", "enum_value": open_state},
                {"key": "open_percentage", "type": "INTEGER", "integer_value": "35"},
            ]
        )
    )
    assert snapshot.state == expected
    assert snapshot.current_position == 35


def test_cover_state_without_reports_is_closed_with_unknown_position():
    snapshot = cover_state_from_dto(_curtain([]))
    assert snapshot.state == CoverState.CLOSED
    assert snapshot.current_position is None


@pytest.mark.parametrize(
    ("ha_mode", "sber"),
    [
        (None, None),
        (HVACMode.OFF, None),
        (HVACMode.COOL, "cool"),
        (HVACMode.FAN_ONLY, "fan_only"),
        (HVACMode.HEAT_COOL, "heat_cool"),
    ],
)
def test_map_hvac_mode_to_sber(ha_mode, sber):
    assert map_hvac_mode_to_sber(ha_mode) == sber


def test_feature_spec_for_known_and_unknown():
    assert feature_spec_for("battery_percentage") is FEATURE_SPECS["battery_percentage"]
    assert feature_spec_for("no_such_feature") is None
