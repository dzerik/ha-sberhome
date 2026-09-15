"""Сервис `sberhome.ttc_send` в настоящем Home Assistant поверх облака в памяти."""

from __future__ import annotations

import json

import httpx
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.sberhome.const import CONF_ENABLED_DEVICE_UIDS, DOMAIN

from .fake_cloud import FakeSberCloud, device


async def _speakers(setup_sberhome, fake_cloud: FakeSberCloud) -> None:
    fake_cloud.homes.append({"id": "home-2", "name": "Дача", "group_type": "HOME"})
    fake_cloud.devices = [
        device("boom", image_set_type="dt_boom"),
        device("portal", image_set_type="dt_portal", group_ids=["home-2"]),
        device("lamp"),
    ]
    fake_cloud.on("POST", "/scenario/v2/scenario", {"id": "sc-ttc"})
    for method in ("PUT", "POST"):
        fake_cloud.on(method, "/scenario/v2/scenario/sc-ttc", {"result": {}})
    fake_cloud.on("POST", "/scenario/v2/scenario/sc-ttc/run", {"result": {}})
    await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: []})


def _commands(fake_cloud: FakeSberCloud) -> list[str]:
    """Тексты команд из последнего обновления сценария-посредника."""
    body = json.loads(fake_cloud.sent("PUT", "/scenario/v2/scenario/sc-ttc")[-1].content)
    return [
        task["head_dialog_command_task_data"]["text"]
        for step in body["steps"]
        for task in step["tasks"]
    ]


async def test_command_template_is_rendered_and_sent_only_to_home_speakers(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    await _speakers(setup_sberhome, fake_cloud)

    response = await hass.services.async_call(
        DOMAIN,
        "ttc_send",
        {"message": "Сколько будет {{ 2 + 2 }}", "device_ids": ["boom"]},
        blocking=True,
        return_response=True,
    )

    assert response == {"ok": True, "results": {"home-1": "ok"}}
    assert _commands(fake_cloud) == ["Сколько будет 4"]
    body = json.loads(fake_cloud.sent("PUT", "/scenario/v2/scenario/sc-ttc")[-1].content)
    assert "portal" not in json.dumps(body)


async def test_broken_template_is_rejected_before_cloud_call(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    await _speakers(setup_sberhome, fake_cloud)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "ttc_send", {"message": "{{ 1 + }}", "device_ids": ["boom"]}, blocking=True
        )

    assert fake_cloud.sent("PUT", "/scenario/v2/scenario/sc-ttc") == []


async def test_cloud_rejecting_update_is_reported(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud
) -> None:
    await _speakers(setup_sberhome, fake_cloud)
    fake_cloud.on("PUT", "/scenario/v2/scenario/sc-ttc", httpx.Response(500, json={}))

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "ttc_send", {"message": "Который час", "device_ids": ["boom"]}, blocking=True
        )

    assert fake_cloud.sent("POST", "/scenario/v2/scenario/sc-ttc/run") == []
