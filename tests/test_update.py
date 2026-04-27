"""Tests для firmware UpdateEntity (OTA)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.coordinator import OTA_POLL_INTERVAL_SEC
from custom_components.sberhome.update import SberFirmwareUpdate


def _coord(*, sw_version: str = "1.0.0", ota: dict | None = None) -> MagicMock:
    coord = MagicMock()
    dto = DeviceDto(id="dev-1", sw_version=sw_version)
    coord.devices = {"dev-1": dto}
    coord.state_cache.get_device = MagicMock(return_value=dto)
    coord.ota_upgrades = ota or {}
    return coord


class TestFirmwareUpdate:
    def test_installed_version_from_dto(self):
        coord = _coord(sw_version="26.1.4")
        upd = SberFirmwareUpdate(coord, "dev-1")
        assert upd.installed_version == "26.1.4"

    def test_no_upgrade_record_means_up_to_date(self):
        """Если /inventory/ota-upgrades ничего не вернул для этого
        device — installed == latest, HA UI покажет «Up to date»."""
        coord = _coord(sw_version="26.1.4")
        upd = SberFirmwareUpdate(coord, "dev-1")
        assert upd.latest_version == "26.1.4"
        assert upd.release_summary is None

    def test_upgrade_record_shows_pending_version(self):
        coord = _coord(
            sw_version="26.1.4",
            ota={
                "dev-1": {
                    "available_version": "26.2.0",
                    "release_notes": "Fix Zigbee pairing.",
                }
            },
        )
        upd = SberFirmwareUpdate(coord, "dev-1")
        assert upd.installed_version == "26.1.4"
        assert upd.latest_version == "26.2.0"
        assert upd.release_summary == "Fix Zigbee pairing."

    def test_falls_back_to_installed_when_upgrade_payload_garbled(self):
        """Sber может вернуть запись без available_version (например пустой
        dict — partner-bridge sometimes does this). Считаем «всё актуально»."""
        coord = _coord(sw_version="1.0.0", ota={"dev-1": {}})
        upd = SberFirmwareUpdate(coord, "dev-1")
        assert upd.latest_version == "1.0.0"

    def test_release_url_passed_through(self):
        coord = _coord(
            sw_version="1.0.0",
            ota={"dev-1": {"available_version": "1.1.0", "release_url": "https://example.com/r"}},
        )
        upd = SberFirmwareUpdate(coord, "dev-1")
        assert upd.release_url == "https://example.com/r"


# ---------------------------------------------------------------------------
# Coordinator.async_refresh_ota / _maybe_poll_ota throttling
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_poll_skips_when_disabled():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._ota_disabled = True
    coord._ota_last_poll_at = None
    api = MagicMock()
    api.list_ota_upgrades = AsyncMock(return_value={})
    coord._inventory_api = MagicMock(return_value=api)

    await SberHomeCoordinator._maybe_poll_ota(coord)
    api.list_ota_upgrades.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_throttled_within_interval():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._ota_disabled = False
    coord._ota_last_poll_at = time.time() - 60  # минуту назад
    api = MagicMock()
    api.list_ota_upgrades = AsyncMock(return_value={})
    coord._inventory_api = MagicMock(return_value=api)

    await SberHomeCoordinator._maybe_poll_ota(coord)
    api.list_ota_upgrades.assert_not_awaited()


@pytest.mark.asyncio
async def test_maybe_poll_runs_after_interval():
    import time

    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._ota_disabled = False
    coord._ota_last_poll_at = time.time() - OTA_POLL_INTERVAL_SEC - 1
    api = MagicMock()
    api.list_ota_upgrades = AsyncMock(return_value={"dev-1": {"available_version": "2.0"}})
    coord._inventory_api = MagicMock(return_value=api)

    await SberHomeCoordinator._maybe_poll_ota(coord)
    api.list_ota_upgrades.assert_awaited_once()
    assert coord.ota_upgrades == {"dev-1": {"available_version": "2.0"}}


@pytest.mark.asyncio
async def test_maybe_poll_disables_on_exception():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._ota_disabled = False
    coord._ota_last_poll_at = None
    api = MagicMock()
    api.list_ota_upgrades = AsyncMock(side_effect=RuntimeError("boom"))
    coord._inventory_api = MagicMock(return_value=api)

    await SberHomeCoordinator._maybe_poll_ota(coord)
    assert coord._ota_disabled is True


@pytest.mark.asyncio
async def test_async_refresh_ota_resets_disabled_and_polls():
    from custom_components.sberhome.coordinator import SberHomeCoordinator

    coord = MagicMock(spec=SberHomeCoordinator)
    coord._ota_disabled = True
    coord.data = {}
    coord.async_set_updated_data = MagicMock()
    api = MagicMock()
    api.list_ota_upgrades = AsyncMock(return_value={"dev-1": {"available_version": "9.0"}})
    coord._inventory_api = MagicMock(return_value=api)

    await SberHomeCoordinator.async_refresh_ota(coord)
    assert coord._ota_disabled is False
    assert coord.ota_upgrades == {"dev-1": {"available_version": "9.0"}}
    coord.async_set_updated_data.assert_called_once()
