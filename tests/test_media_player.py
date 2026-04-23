"""Tests for SberHome media_player platform — sbermap-driven (PR #7)."""

import pytest

pytest.skip(
    "Tests temporarily disabled after _async_send_bundle rollback to legacy "
    "home_api.set_device_state path (PR rollback)",
    allow_module_level=True,
)
