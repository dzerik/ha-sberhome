"""Сценарии, сопряжение и сценарии-посредники TTS/TTC в панели.

Облако отвечает ошибкой — панель получает её код и текст, а не таймаут.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from homeassistant.core import HomeAssistant

from custom_components.sberhome.const import CONF_ENABLED_DEVICE_UIDS

from ..fake_cloud import FakeSberCloud, device
from .conftest import Panel

SCENARIO = {"id": "sc-1", "name": "Утро", "steps": [], "home_id": "home-1"}
SPEC = {"name": "Утро", "phrases": ["доброе утро"], "actions": []}
FAILURE = httpx.Response(500, json={"message": "upstream exploded"})


async def _loaded(setup_sberhome, fake_cloud: FakeSberCloud, *devices: dict[str, Any]) -> None:
    fake_cloud.devices = list(devices) or [device("lamp")]
    await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp"]})


@pytest.mark.parametrize(
    "payload",
    [
        {"result": [SCENARIO]},
        [SCENARIO, "garbage"],
        {"scenarios": [SCENARIO], "pagination": {}, "extra": 1},
    ],
    ids=["result-list", "bare-list", "scenarios-with-siblings"],
)
async def test_intent_list_accepts_every_response_shape_and_fills_last_fired(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    panel: Panel,
    payload: Any,
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    fake_cloud.on("GET", "/scenario/v2/scenario", payload)
    fake_cloud.on(
        "GET",
        "/scenario/v2/event",
        {
            "events": [
                {"object_id": "sc-1", "event_time": "2026-09-01T10:00:00Z"},
                {"object_id": "sc-1", "event_time": "2026-09-02T10:00:00Z"},
                {"object_id": "sc-1"},
            ]
        },
    )

    response = await panel("intents/list")

    intents = response["result"]["intents"]
    assert [i["id"] for i in intents] == ["sc-1"]
    assert intents[0]["last_fired_at"] == "2026-09-02T10:00:00Z"


async def test_intent_list_of_unexpected_payload_is_empty(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    fake_cloud.on("GET", "/scenario/v2/scenario", "unexpected")

    assert (await panel("intents/list"))["result"] == {"intents": []}


async def test_intent_commands_surface_cloud_errors(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    for method in ("GET", "PUT", "DELETE"):
        fake_cloud.on(method, "/scenario/v2/scenario/sc-1", FAILURE)

    get = await panel("intents/get", intent_id="sc-1")
    update = await panel("intents/update", intent_id="sc-1", spec=SPEC)
    delete = await panel("intents/delete", intent_id="sc-1")
    run = await panel("intents/test", intent_id="sc-1")

    assert get["error"]["code"] == "fetch_failed"
    assert update["error"]["code"] == "update_failed"
    assert delete["error"]["code"] == "delete_failed"
    assert run["error"]["code"] == "test_failed"


async def test_intent_test_of_missing_scenario_fails_without_running(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    fake_cloud.on("GET", "/scenario/v2/scenario/sc-9", {"result": {}})

    response = await panel("intents/test", intent_id="sc-9")

    assert response["error"]["code"] == "test_failed"
    assert fake_cloud.sent("POST", "/scenario/v2/scenario/sc-9/run") == []


async def test_intent_schema_lists_action_types(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)

    response = await panel("intents/schema")

    assert response["result"]["action_types"]


async def test_matter_commands_surface_cloud_errors(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    fake_cloud.on("GET", "/devices/categories/matter", FAILURE)
    fake_cloud.on("POST", "/devices/matter/noc", FAILURE)
    fake_cloud.on("POST", "/devices/matter/complete", {"result": {"done": True}})

    categories = await panel("pairing/matter_categories")
    noc = await panel("pairing/matter_noc", payload={"csr": "x"})
    complete = await panel("pairing/matter_complete")

    assert categories["error"]["code"] == "fetch_failed"
    assert noc["error"]["code"] == "matter_failed"
    assert complete["result"] == {"done": True}
    assert fake_cloud.body(fake_cloud.sent("POST", "/devices/matter/noc")[0]) == {"csr": "x"}
    assert fake_cloud.body(fake_cloud.sent("POST", "/devices/matter/complete")[0]) == {}


SPEAKER = device(
    "boom",
    image_set_type="dt_boom",
    name="",
    reported=[{"key": "online", "type": "BOOL", "bool_value": True}],
)
SPEAKER["name"] = {"name": "", "defaultName": "Колонка"}
OTHER_HOME_SPEAKER = device("portal", image_set_type="dt_portal", group_ids=["home-2"])
UNNAMED_SPEAKER = device("box", image_set_type="dt_box", name="")
UNNAMED_SPEAKER["name"] = {"name": ""}


@pytest.mark.parametrize("kind", ["tts", "ttc"])
async def test_surrogate_status_lists_speakers_per_home(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    panel: Panel,
    kind: str,
) -> None:
    fake_cloud.homes.append({"id": "home-2", "name": "Дача", "group_type": "HOME"})
    await _loaded(
        setup_sberhome, fake_cloud, SPEAKER, OTHER_HOME_SPEAKER, UNNAMED_SPEAKER, device("lamp")
    )

    response = await panel(f"{kind}_surrogate/status")

    homes = {h["home_id"]: h for h in response["result"]["homes"]}
    assert homes["home-1"]["speakers"] == [
        {"id": "boom", "name": "Колонка", "online": True},
        {"id": "box", "name": "box", "online": None},
    ]
    assert homes["home-2"]["speakers"] == [{"id": "portal", "name": "portal", "online": None}]
    assert homes["home-1"]["scenario_id"] is None


@pytest.mark.parametrize("kind", ["tts", "ttc"])
async def test_surrogate_status_falls_back_to_cache_when_cloud_fails(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    panel: Panel,
    kind: str,
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    coordinator = hass.config_entries.async_entries("sberhome")[0].runtime_data
    getattr(coordinator, f"{kind}_surrogates")["home-1"] = "cached-sc"
    fake_cloud.on("GET", "/scenario/v2/scenario", FAILURE)

    response = await panel(f"{kind}_surrogate/status")

    assert response["result"]["homes"][0]["scenario_id"] == "cached-sc"


@pytest.mark.parametrize("kind", ["tts", "ttc"])
async def test_surrogate_ensure_and_test_report_cloud_errors(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    panel: Panel,
    kind: str,
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    fake_cloud.on("GET", "/scenario/v2/scenario", FAILURE)

    ensure = await panel(f"{kind}_surrogate/ensure", home_id="home-1")
    test = await panel(f"{kind}_surrogate/test", home_id="home-1", message="привет")

    assert ensure["result"]["ok"] is False
    assert ensure["result"]["error"]
    assert test["result"]["ok"] is False
    assert test["result"]["error"]


@pytest.mark.parametrize("kind", ["tts", "ttc"])
async def test_surrogate_ensure_for_home_without_speakers_names_the_home(
    hass: HomeAssistant,
    setup_sberhome,
    fake_cloud: FakeSberCloud,
    panel: Panel,
    kind: str,
) -> None:
    await _loaded(setup_sberhome, fake_cloud)

    known = await panel(f"{kind}_surrogate/ensure", home_id="home-1")
    unknown = await panel(f"{kind}_surrogate/ensure", home_id="home-gone")

    assert known["result"]["ok"] is False
    assert "Дом" in known["result"]["error"]
    # Дома нет в кэше — в ошибке его id, а не пустое имя.
    assert "home-gone" in unknown["result"]["error"]
    assert fake_cloud.sent("POST", "/scenario/v2/scenario") == []
