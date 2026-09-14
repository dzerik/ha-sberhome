"""Настройки панели: типы, диапазоны, значения по умолчанию, применение без перезагрузки."""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.sberhome.settings import (
    LIVE_SETTINGS,
    SETTINGS_DEFAULTS,
    SETTINGS_LIMITS,
    SETTINGS_SCHEMA,
    only_live_settings_changed,
    read_settings,
)


def test_defaults_cover_every_validated_key() -> None:
    assert set(SETTINGS_DEFAULTS) == {str(k) for k in SETTINGS_SCHEMA.schema}
    assert set(SETTINGS_LIMITS) == set(SETTINGS_DEFAULTS)


def test_read_settings_fills_defaults_and_ignores_other_options() -> None:
    options = {"scan_interval": 60, "enabled_device_uids": ["x"]}
    assert read_settings(options) == {**SETTINGS_DEFAULTS, "scan_interval": 60}


@pytest.mark.parametrize(
    "bad",
    [
        {"scan_interval": "60"},
        {"scan_interval": True},
        {"scan_interval": 9},
        {"devtools_buffer_size": 5001},
        {"command_timeout": 0},
        {"command_timeout": "10"},
    ],
)
def test_schema_rejects_wrong_types_and_ranges(bad: dict) -> None:
    with pytest.raises(vol.Invalid):
        SETTINGS_SCHEMA(bad)


def test_schema_accepts_bounds_and_drops_unknown_keys() -> None:
    low = {k: v["min"] for k, v in SETTINGS_LIMITS.items()}
    high = {k: v["max"] for k, v in SETTINGS_LIMITS.items()}
    assert SETTINGS_SCHEMA({**low, "junk": 1}) == low
    assert SETTINGS_SCHEMA(high) == high


def test_command_timeout_accepts_integers() -> None:
    assert SETTINGS_SCHEMA({"command_timeout": 15}) == {"command_timeout": 15.0}


@pytest.mark.parametrize(
    ("before", "after", "live"),
    [
        ({"scan_interval": 30}, {"scan_interval": 60}, True),
        ({}, {"devtools_buffer_size": 500, "command_timeout": 20.0}, True),
        ({"enabled_device_uids": ["a"]}, {"enabled_device_uids": ["a", "b"]}, False),
        ({"scan_interval": 30}, {"scan_interval": 60, "enabled_device_uids": ["a"]}, False),
        ({"scan_interval": 30}, {"scan_interval": 30}, False),
    ],
)
def test_only_live_settings_changed(before: dict, after: dict, live: bool) -> None:
    assert only_live_settings_changed(before, after) is live
    assert frozenset(SETTINGS_DEFAULTS) == LIVE_SETTINGS
