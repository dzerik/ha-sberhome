"""Tests for sbermap.ws_apply (PR #11)."""

from __future__ import annotations

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.aiosber.dto.values import (
    AttributeValueDto,
    AttributeValueType,
)
from custom_components.sberhome.sbermap import apply_reported_state


def _dto(
    *, reported: list[AttributeValueDto] | None = None
) -> DeviceDto:
    return DeviceDto(
        id="d1",
        name="Test",
        image_set_type="bulb_sber",
        reported_state=reported or [],
    )


class TestApplyReportedState:
    def test_empty_payload_returns_same_dto(self):
        dto = _dto(reported=[
            AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=False)
        ])
        out = apply_reported_state(dto, [])
        assert out is dto

    def test_replace_existing_key(self):
        dto = _dto(reported=[
            AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=False),
            AttributeValueDto(
                key="temperature",
                type=AttributeValueType.INTEGER,
                integer_value=200,
            ),
        ])
        new = apply_reported_state(dto, [
            AttributeValueDto(
                key="temperature",
                type=AttributeValueType.INTEGER,
                integer_value=225,
            ),
        ])
        assert new is not dto  # immutable
        # on_off остался, temperature заменился
        by_key = {av.key: av for av in new.reported_state}
        assert by_key["on_off"].bool_value is False
        assert by_key["temperature"].integer_value == 225

    def test_adds_new_key(self):
        dto = _dto(reported=[
            AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=False)
        ])
        new = apply_reported_state(dto, [
            AttributeValueDto(
                key="humidity",
                type=AttributeValueType.INTEGER,
                integer_value=42,
            ),
        ])
        keys = {av.key for av in new.reported_state}
        assert keys == {"on_off", "humidity"}

    def test_does_not_touch_desired_state(self):
        dto = DeviceDto(
            id="d1",
            image_set_type="bulb_sber",
            desired_state=[
                AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True)
            ],
        )
        new = apply_reported_state(dto, [
            AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=False)
        ])
        # desired_state не изменился
        assert new.desired_state == dto.desired_state
