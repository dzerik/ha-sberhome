"""Tests for the SberHome auth state module."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.sberhome.auth_state import pending_auth_flows


def test_pending_auth_flows_is_dict():
    assert isinstance(pending_auth_flows, dict)


def test_pending_auth_flows_add_and_remove():
    mock_client = MagicMock()
    pending_auth_flows["test-flow"] = mock_client
    assert pending_auth_flows["test-flow"] is mock_client
    pending_auth_flows.pop("test-flow", None)
    assert "test-flow" not in pending_auth_flows
