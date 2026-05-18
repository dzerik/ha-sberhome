"""Tests for the conflicting-integration detector."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from custom_components.sberhome.conflict import (
    CONFLICTING_DOMAINS,
    ISSUE_ID,
    async_update_conflict_issue,
    detect_conflicts,
)
from custom_components.sberhome.const import DOMAIN


def _hass_with_entries(entries_by_domain: dict[str, list]) -> MagicMock:
    """MagicMock hass где config_entries.async_entries(domain) → список."""
    hass = MagicMock()
    hass.config_entries.async_entries.side_effect = lambda domain: entries_by_domain.get(domain, [])
    return hass


def test_detect_conflicts_finds_sberdevices():
    hass = _hass_with_entries({"sberdevices": [MagicMock()]})
    assert detect_conflicts(hass) == ["sberdevices"]


def test_detect_conflicts_empty_when_no_other_integration():
    hass = _hass_with_entries({})
    assert detect_conflicts(hass) == []


def test_detect_conflicts_ignores_empty_entry_list():
    """Интеграция установлена, но без сконфигурированных entries — не конфликт."""
    hass = _hass_with_entries({"sberdevices": []})
    assert detect_conflicts(hass) == []


def test_update_conflict_issue_creates_when_conflict():
    hass = _hass_with_entries({"sberdevices": [MagicMock()]})
    with (
        patch("custom_components.sberhome.conflict.ir.async_create_issue") as create,
        patch("custom_components.sberhome.conflict.ir.async_delete_issue") as delete,
    ):
        result = async_update_conflict_issue(hass)

    assert result == ["sberdevices"]
    delete.assert_not_called()
    create.assert_called_once()
    args, kwargs = create.call_args
    assert args[:3] == (hass, DOMAIN, ISSUE_ID)
    assert kwargs["translation_key"] == ISSUE_ID
    assert kwargs["translation_placeholders"] == {"domains": "sberdevices"}


def test_update_conflict_issue_deletes_when_no_conflict():
    hass = _hass_with_entries({})
    with (
        patch("custom_components.sberhome.conflict.ir.async_create_issue") as create,
        patch("custom_components.sberhome.conflict.ir.async_delete_issue") as delete,
    ):
        result = async_update_conflict_issue(hass)

    assert result == []
    create.assert_not_called()
    delete.assert_called_once_with(hass, DOMAIN, ISSUE_ID)


def test_conflicting_domains_does_not_include_own_domain():
    """Защита от регрессии: собственный домен не должен попасть в список."""
    assert DOMAIN not in CONFLICTING_DOMAINS
