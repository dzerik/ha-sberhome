"""Настройка интеграции в настоящем Home Assistant поверх облака в памяти.

YAML-секция `sberhome:`, вход по SMS, обновление и миграция записи.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome._ha_token_store import HACsafrontTokenStore
from custom_components.sberhome.aiosber.auth import CsafrontTokens
from custom_components.sberhome.const import CONF_AUTH_METHOD, CONF_ENABLED_DEVICE_UIDS, DOMAIN

from .fake_cloud import FakeSberCloud, device

INTENT = {"name": "Утро", "phrases": ["доброе утро"], "actions": [{"type": "ha_event_only"}]}


def _listener(name: str, **filter_: Any) -> dict[str, Any]:
    return {"name": name, "filter": filter_}


async def test_yaml_intents_are_created_and_listener_homes_resolved(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    fake_cloud.homes.append({"id": "home-2", "name": "Дача", "group_type": "HOME"})
    fake_cloud.on("POST", "/scenario/v2/scenario", {"result": {"id": "sc-new", "name": "Утро"}})
    entry = await setup_sberhome(
        options={},
        config={
            "intents": [
                INTENT,
                {**INTENT, "name": "На даче", "home": "Дача"},
                {**INTENT, "name": "Дома", "home_id": "home-1"},
            ],
            "listeners": [
                _listener("По имени", home="  дача "),
                _listener("По id", home_id="home-1"),
                _listener("Любой дом", trigger_type="TIME"),
                _listener("Нет такого", home="Квартира"),
            ],
        },
    )

    assert entry.state is ConfigEntryState.LOADED
    created = {
        body["name"]: body.get("home_id")
        for body in map(fake_cloud.body, fake_cloud.sent("POST", "/scenario/v2/scenario"))
    }
    # Без явного дома — дом по умолчанию (первый), иначе заданный в YAML.
    assert created == {"Утро": "home-1", "На даче": "home-2", "Дома": "home-1"}
    listeners = {s.name: s for s in entry.runtime_data.listener_registry.list()}
    assert listeners["По имени"].filter.home_id == "home-2"
    assert listeners["По id"].filter.home_id == "home-1"
    assert listeners["Любой дом"].filter.home_id is None
    assert listeners["Нет такого"].enabled is False
    assert all(listeners[n].enabled for n in ("По имени", "По id", "Любой дом"))


@pytest.mark.parametrize("section", ["intents", "listeners"])
async def test_yaml_with_duplicate_slugs_is_ignored_but_entry_loads(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    caplog: pytest.LogCaptureFixture,
    section: str,
) -> None:
    items = (
        [INTENT, {**INTENT, "phrases": ["другая"]}]
        if section == "intents"
        else [_listener("Тот же", trigger_type="TIME"), _listener("Тот же", trigger_type="TIME")]
    )

    entry = await setup_sberhome(options={}, config={section: items})

    assert entry.state is ConfigEntryState.LOADED
    assert f"sberhome.{section}" in caplog.text
    assert fake_cloud.sent("POST", "/scenario/v2/scenario") == []
    assert entry.runtime_data.listener_registry.list() == []


async def test_sms_login_entry_uses_smart_home_token(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    fake_cloud.devices = [device("lamp")]
    tokens = CsafrontTokens(
        csafront_access_token="csa",
        csafront_refresh_token="csr",
        smart_home_token="sms-smart-home",
        client_uuid="uuid-1",
        csafront_obtained_at=time.time(),
    )

    entry = await setup_sberhome(
        options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp"]},
        data={CONF_AUTH_METHOD: "csafront", "csafront_tokens": tokens.to_dict()},
    )

    assert entry.state is ConfigEntryState.LOADED
    (devices_request,) = fake_cloud.sent("GET", "/devices")[:1]
    assert devices_request.headers["X-AUTH-jwt"] == "sms-smart-home"
    # У SMS-входа нет токена канала настроек колонок.
    assert entry.runtime_data.has_staros_settings() is False


async def test_csafront_token_store_persists_in_entry_data(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(domain=DOMAIN, data={"token": {"access_token": "keep"}})
    entry.add_to_hass(hass)
    store = HACsafrontTokenStore(hass, entry)
    tokens = CsafrontTokens(
        csafront_access_token="a",
        csafront_refresh_token="r",
        smart_home_token="s",
        client_uuid="u",
    )
    assert await store.load() is None

    await store.save_refreshed(tokens)
    assert entry.data["token"] == {"access_token": "keep"}
    assert await store.load() == tokens

    await store.clear()
    assert entry.data == {"token": {"access_token": "keep"}}
    assert await store.load() is None


async def test_token_rotation_in_entry_data_does_not_reload(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    fake_cloud.devices = [device("lamp")]
    entry = await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp"]})
    coordinator = entry.runtime_data

    hass.config_entries.async_update_entry(entry, data={**entry.data, "rotated": True})
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is coordinator


async def test_entry_from_newer_version_is_not_downgraded(
    hass: HomeAssistant, setup_sberhome, caplog: pytest.LogCaptureFixture
) -> None:
    entry = await setup_sberhome(options={}, version=4)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR
    assert entry.version == 4
    assert "Cannot downgrade" in caplog.text
