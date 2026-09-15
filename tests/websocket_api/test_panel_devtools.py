"""Инструменты разработчика в панели: журнал, проверка схемы, повтор сообщений,
состояние интеграции и ручные обновления — через настоящий WebSocket."""

from __future__ import annotations

from typing import Any

import httpx
from homeassistant.core import HomeAssistant

from custom_components.sberhome.const import CONF_ENABLED_DEVICE_UIDS

from ..fake_cloud import FakeSberCloud, device
from .conftest import Panel


def _state_push(device_id: str, *attrs: dict[str, Any]) -> dict[str, Any]:
    return {"state": {"device_id": device_id, "reported_state": list(attrs)}}


ON = {"key": "on_off", "type": "BOOL", "bool_value": True}
OFF = {"key": "on_off", "type": "BOOL", "bool_value": False}


async def _loaded(setup_sberhome, fake_cloud: FakeSberCloud) -> None:
    fake_cloud.devices = [device("lamp", reported=[OFF])]
    await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-lamp"]})


async def test_message_log_streams_injected_push_and_clears(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)

    subscribe = await panel("subscribe_messages")
    assert subscribe["success"]
    assert await panel.event(subscribe["id"]) == {"snapshot": []}

    injected = await panel("inject_ws_message", payload=_state_push("lamp", ON))
    assert injected["result"] == {"topic": "device_state", "handled": True, "device_id": "lamp"}
    live = await panel.event(subscribe["id"])
    assert live["message"]["direction"] == "replay"
    assert live["message"]["device_id"] == "lamp"
    # Инъекция проходит тем же путём, что и настоящий push.
    assert hass.states.get("light.lamp").state == "on"

    log = await panel("message_log")
    assert [m["topic"] for m in log["result"]["messages"]] == ["DEVICE_STATE"]

    unsubscribe = {"type": "unsubscribe_events", "subscription": subscribe["id"]}
    assert (await panel.raw(unsubscribe))["success"]
    await panel("replay_ws_message", payload=_state_push("lamp", OFF))
    await panel("message_log")
    assert panel.pending_events(subscribe["id"]) == []
    cleared = await panel("clear_message_log")
    assert cleared["result"] == {"success": True}
    assert (await panel("message_log"))["result"]["messages"] == []


async def test_inject_real_topic_is_logged_as_incoming_when_not_marked(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)

    widgets = await panel(
        "inject_ws_message",
        payload={"scenario_widget": {"type": "UPDATE_WIDGETS"}},
        mark_replay=False,
    )
    ota = await panel("replay_ws_message", payload={"fw_task_status": {"device_id": "lamp"}})
    empty = await panel("inject_ws_message", payload={"unknown": 1})

    assert widgets["result"]["handled"] is True
    assert ota["result"]["handled"] is True
    assert empty["result"] == {"topic": None, "handled": False, "device_id": None}
    messages = (await panel("message_log"))["result"]["messages"]
    assert [(m["topic"], m["direction"]) for m in messages] == [
        ("scenario_widgets", "in"),
        ("inventory_ota", "replay"),
        ("INJECT", "replay"),
    ]


async def test_inject_reports_payload_the_handlers_cannot_apply(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    """Payload, на котором разбор состояния падает, возвращает ошибку, а не таймаут."""
    fake_cloud.devices = [device("ac", image_set_type="hvac_ac")]
    await setup_sberhome(options={CONF_ENABLED_DEVICE_UIDS: ["SN-ac"]})
    broken = _state_push("ac", {"key": "temperature", "type": "INTEGER", "integer_value": "zz"})

    inject = await panel("inject_ws_message", payload=broken)
    replay = await panel("replay_ws_message", payload=broken)

    assert inject["error"]["code"] == "inject_failed"
    assert replay["error"]["code"] == "replay_failed"


async def test_validation_issues_stream_snapshot_and_clear(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)

    subscribe = await panel("subscribe_validation_issues")
    assert subscribe["success"]
    assert (await panel.event(subscribe["id"]))["snapshot"]["recent"] == []

    await panel(
        "inject_ws_message",
        payload=_state_push("lamp", {"key": "made_up_key", "type": "BOOL", "bool_value": True}),
    )
    event = await panel.event(subscribe["id"])
    assert event["issues"][0]["device_id"] == "lamp"

    issues = await panel("validation_issues")
    assert "lamp" in issues["result"]["by_device"]

    unsubscribe = {"type": "unsubscribe_events", "subscription": subscribe["id"]}
    assert (await panel.raw(unsubscribe))["success"]
    await panel(
        "inject_ws_message",
        payload=_state_push("lamp", {"key": "other_made_up", "type": "BOOL", "bool_value": True}),
    )
    assert panel.pending_events(subscribe["id"]) == []
    assert (await panel("clear_validation_issues"))["result"] == {"success": True}
    assert (await panel("validation_issues"))["result"] == {"recent": [], "by_device": {}}


async def test_status_of_legacy_entry_without_stored_selection(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    fake_cloud.devices = [device("lamp")]
    entry = await setup_sberhome(options={})

    response = await panel("get_status")

    result = response["result"]
    assert result["entry_id"] == entry.entry_id
    assert result["version"]
    assert result["selection"] == {"stored": None, "resolved": None, "unresolved": 0}
    assert result["devices_enabled"] == result["devices_total"] == 1
    assert result["ws"]["message_count"] == 0


async def test_refresh_ota_reports_cloud_failure(
    hass: HomeAssistant, setup_sberhome, fake_cloud: FakeSberCloud, panel: Panel
) -> None:
    await _loaded(setup_sberhome, fake_cloud)
    fake_cloud.on("GET", "/inventory/ota-upgrades", {"result": {"lamp": {"version": "2"}}})
    ok = await panel("refresh_ota")
    fake_cloud.on("GET", "/inventory/ota-upgrades", httpx.Response(500, json={}))
    failed = await panel("refresh_ota")

    assert ok["result"] == {"success": True, "device_count": 1}
    assert failed["error"]["code"] == "refresh_failed"
