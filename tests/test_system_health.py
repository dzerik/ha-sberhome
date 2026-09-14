"""Сводка на странице «Сведения о системе»."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.sberhome.system_health import system_health_info

MODULE = "custom_components.sberhome.system_health"


def _coord() -> MagicMock:
    coord = MagicMock()
    coord.devices = {"a": object(), "b": object()}
    coord.enabled_device_ids = {"a"}
    coord.enabled_device_uids = ["a"]
    coord.last_update_success = True
    coord.ws_connected = False
    coord.consecutive_failures = 0
    coord.last_polling_at = 1_700_000_000.4
    coord.registry_maintenance_failures = 0
    coord.auth_manager = SimpleNamespace()
    coord.disabled_background_polls = MagicMock(return_value=[])
    return coord


async def test_info_summarises_the_coordinator(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "system_health", {})
    with (
        patch(f"{MODULE}.get_coordinator", return_value=_coord()),
        patch(f"{MODULE}.get_config_entry", return_value=MagicMock()),
    ):
        info = await system_health_info(hass)
    info.pop("can_reach_gateway").close()
    assert info == {
        "state": "degraded",
        "problems": "ws_disconnected",
        "websocket": "disconnected",
        "last_poll": 1_700_000_000,
        "failed_updates_in_a_row": 0,
        "devices_total": 2,
        "devices_enabled": 1,
    }


async def test_not_loaded(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "system_health", {})
    with (
        patch(f"{MODULE}.get_coordinator", return_value=None),
        patch(f"{MODULE}.get_config_entry", return_value=None),
    ):
        info = await system_health_info(hass)
    info.pop("can_reach_gateway").close()
    assert info == {"state": "not_loaded"}


def test_every_info_key_is_labelled_in_every_language() -> None:
    keys = {
        "can_reach_gateway",
        "state",
        "problems",
        "websocket",
        "last_poll",
        "failed_updates_in_a_row",
        "devices_total",
        "devices_enabled",
    }
    base = Path(__file__).resolve().parents[1] / "custom_components" / "sberhome"
    for path in [base / "strings.json", *sorted((base / "translations").glob("*.json"))]:
        labels = json.loads(path.read_text(encoding="utf-8"))["system_health"]["info"]
        assert set(labels) == keys, path.name
