"""WS endpoints для voice intents — поверх IntentService."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.sberhome.aiosber.dto.device import DeviceDto
from custom_components.sberhome.intents.encoder import decode_scenario, encode_scenario
from custom_components.sberhome.intents.service import IntentService
from custom_components.sberhome.intents.spec import IntentAction, IntentSpec
from custom_components.sberhome.websocket_api.intents import (
    ws_create_intent,
    ws_delete_intent,
    ws_devices_for_picker,
    ws_get_intent,
    ws_intent_schema,
    ws_list_intents,
    ws_test_intent,
    ws_update_intent,
)


@pytest.fixture
def connection():
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture
def hass():
    return MagicMock()


def _patch_service(service: MagicMock):
    return patch(
        "custom_components.sberhome.websocket_api.intents._service",
        return_value=service,
    )


def _make_service(**methods):
    s = MagicMock()
    s.list_intents = AsyncMock(return_value=methods.get("list", []))
    s.get_intent = AsyncMock(return_value=methods.get("get"))
    s.create_intent = AsyncMock(return_value=methods.get("create"))
    s.update_intent = AsyncMock(return_value=methods.get("update"))
    s.delete_intent = AsyncMock(return_value=None)
    s.test_intent = AsyncMock(return_value=methods.get("test", {"ok": True}))
    return s


# ---------------------------------------------------------------------------
# list / get / schema
# ---------------------------------------------------------------------------


class TestList:
    @pytest.mark.asyncio
    async def test_returns_serialised_specs(self, hass, connection):
        spec = IntentSpec(id="sc-1", name="X", phrases=["x"])
        service = _make_service(list=[spec])
        with _patch_service(service):
            await ws_list_intents.__wrapped__(hass, connection, {"id": 1})
        result = connection.send_result.call_args[0][1]
        assert "intents" in result
        assert result["intents"][0]["id"] == "sc-1"
        assert result["intents"][0]["name"] == "X"

    @pytest.mark.asyncio
    async def test_no_coordinator_returns_error(self, hass, connection):
        with _patch_service(None):
            await ws_list_intents.__wrapped__(hass, connection, {"id": 2})
        assert connection.send_error.call_args[0][1] == "not_loaded"

    @pytest.mark.asyncio
    async def test_service_error_surfaces(self, hass, connection):
        service = _make_service()
        service.list_intents.side_effect = RuntimeError("boom")
        with _patch_service(service):
            await ws_list_intents.__wrapped__(hass, connection, {"id": 3})
        assert connection.send_error.call_args[0][1] == "fetch_failed"


class TestGet:
    @pytest.mark.asyncio
    async def test_known_id(self, hass, connection):
        spec = IntentSpec(id="sc-1", name="X", phrases=["x"])
        service = _make_service(get=spec)
        with _patch_service(service):
            await ws_get_intent.__wrapped__(hass, connection, {"id": 4, "intent_id": "sc-1"})
        # connection.send_result called с serialized spec
        result = connection.send_result.call_args[0][1]
        assert result["id"] == "sc-1"

    @pytest.mark.asyncio
    async def test_missing_returns_not_found(self, hass, connection):
        service = _make_service(get=None)
        with _patch_service(service):
            await ws_get_intent.__wrapped__(hass, connection, {"id": 5, "intent_id": "missing"})
        assert connection.send_error.call_args[0][1] == "not_found"


class TestSchema:
    @pytest.mark.asyncio
    async def test_returns_action_types(self, hass, connection):
        # ws_intent_schema требует только наличие coord (для consistency).
        with patch(
            "custom_components.sberhome.websocket_api.intents.get_coordinator",
            return_value=MagicMock(),
        ):
            await ws_intent_schema.__wrapped__(hass, connection, {"id": 6})
        result = connection.send_result.call_args[0][1]
        assert "action_types" in result
        types = {a["type"] for a in result["action_types"]}
        # Все встроенные actions из registry должны быть.
        assert "tts" in types
        assert "device_command" in types
        assert "ha_event_only" in types


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


class TestCreate:
    @pytest.mark.asyncio
    async def test_creates_and_returns_spec(self, hass, connection):
        created = IntentSpec(id="new-sc", name="X", phrases=["x"])
        service = _make_service(create=created)
        spec_payload = {
            "name": "X",
            "phrases": ["x"],
            "actions": [{"type": "ha_event_only", "data": {}}],
        }
        with _patch_service(service):
            await ws_create_intent.__wrapped__(hass, connection, {"id": 7, "spec": spec_payload})
        result = connection.send_result.call_args[0][1]
        assert result["id"] == "new-sc"

    @pytest.mark.asyncio
    async def test_create_failure_surfaces(self, hass, connection):
        service = _make_service()
        service.create_intent.side_effect = RuntimeError("bad image")
        spec_payload = {"name": "X", "phrases": ["x"], "actions": []}
        with _patch_service(service):
            await ws_create_intent.__wrapped__(hass, connection, {"id": 8, "spec": spec_payload})
        assert connection.send_error.call_args[0][1] == "create_failed"


class TestUpdate:
    @pytest.mark.asyncio
    async def test_updates_existing(self, hass, connection):
        updated = IntentSpec(id="sc-1", name="Renamed", phrases=["x"])
        service = _make_service(update=updated)
        spec_payload = {
            "id": "sc-1",
            "name": "Renamed",
            "phrases": ["x"],
            "actions": [],
            "raw_extras": {"image": "https://..."},
        }
        with _patch_service(service):
            await ws_update_intent.__wrapped__(
                hass, connection, {"id": 9, "intent_id": "sc-1", "spec": spec_payload}
            )
        result = connection.send_result.call_args[0][1]
        assert result["name"] == "Renamed"

    @pytest.mark.parametrize("with_unknown", [False, True])
    async def test_save_and_reopen_preserves_action_order(self, hass, connection, with_unknown):
        """Real WS → service → encoder → mocked cloud → decoder, including read-only data."""
        actions = [
            IntentAction(
                type="device_command",
                data={
                    "device_id": "lamp-1",
                    "attributes": [{"key": "on_off", "type": "BOOL", "bool_value": True}],
                    "delay_seconds": 15,
                },
            ),
            IntentAction(type="tts", data={"phrase": "Готово", "device_ids": ["speaker-1"]}),
            IntentAction(type="trigger_notify"),
        ]
        if with_unknown:
            actions.insert(
                1,
                IntentAction(
                    type="FUTURE_COMMAND",
                    unknown=True,
                    data={"raw": {"type": "FUTURE_COMMAND", "opaque": {"value": 42}}},
                ),
            )
        stored = encode_scenario(IntentSpec(name="Порядок", phrases=["проверка"], actions=actions))
        stored["id"] = "sc-1"
        original_tasks = deepcopy(stored["steps"][0]["tasks"])
        coord = MagicMock()
        coord.state_cache.get_homes.return_value = []

        async def get(_path):
            return MagicMock(json=lambda: deepcopy(stored))

        async def put(_path, *, json):
            stored.clear()
            stored.update(deepcopy(json))
            return MagicMock(json=lambda: deepcopy(stored))

        coord.client.transport.get = AsyncMock(side_effect=get)
        coord.client.transport.put = AsyncMock(side_effect=put)
        with _patch_service(IntentService(coord)):
            await ws_get_intent.__wrapped__(hass, connection, {"id": 20, "intent_id": "sc-1"})
            payload = deepcopy(connection.send_result.call_args.args[1])
            assert payload["is_ha_managed"] is not with_unknown
            if not with_unknown:
                payload["actions"] = [payload["actions"][i] for i in (2, 0, 1)]
            payload["name"] = "Новый порядок"
            await ws_update_intent.__wrapped__(
                hass, connection, {"id": 21, "intent_id": "sc-1", "spec": payload}
            )
            assert connection.send_result.call_args.args[1]["actions"] == payload["actions"]
            await ws_get_intent.__wrapped__(hass, connection, {"id": 22, "intent_id": "sc-1"})

        connection.send_error.assert_not_called()
        reopened = connection.send_result.call_args.args[1]
        assert reopened["actions"] == payload["actions"]
        assert reopened["name"] == "Новый порядок"
        expected = original_tasks if with_unknown else [original_tasks[i] for i in (2, 0, 1)]
        assert stored["steps"][0]["tasks"] == expected


class TestDelete:
    @pytest.mark.asyncio
    async def test_deletes(self, hass, connection):
        service = _make_service()
        with _patch_service(service):
            await ws_delete_intent.__wrapped__(hass, connection, {"id": 10, "intent_id": "sc-1"})
        result = connection.send_result.call_args[0][1]
        assert result == {"success": True}


class TestTest:
    @pytest.mark.asyncio
    async def test_runs_intent(self, hass, connection):
        service = _make_service(test={"ok": True, "scenario_id": "sc-1"})
        with _patch_service(service):
            await ws_test_intent.__wrapped__(hass, connection, {"id": 11, "intent_id": "sc-1"})
        result = connection.send_result.call_args[0][1]
        assert result["success"] is True


# ---------------------------------------------------------------------------
# devices_for_picker — критично!
# ---------------------------------------------------------------------------


class TestDevicesForPicker:
    def _coord_with_devices(self, devices: list[DeviceDto]):
        coord = MagicMock()
        coord.state_cache.get_all_devices = MagicMock(return_value={d.id: d for d in devices})
        coord.state_cache.device_room = MagicMock(return_value=None)
        return coord

    def test_filter_by_category(self, hass, connection):
        coord = self._coord_with_devices(
            [
                DeviceDto(id="speaker-1", image_set_type="dt_boom_r2_dark_blue_s"),
                DeviceDto(id="lamp-1", image_set_type="dt_bulb_e27_m"),
            ]
        )
        with patch(
            "custom_components.sberhome.websocket_api.intents.get_coordinator",
            return_value=coord,
        ):
            ws_devices_for_picker(hass, connection, {"id": 12, "category": "sber_speaker"})
        result = connection.send_result.call_args[0][1]
        assert len(result["devices"]) == 1
        assert result["devices"][0]["device_id"] == "speaker-1"
        assert result["devices"][0]["category"] == "sber_speaker"

    def test_no_filter_returns_all(self, hass, connection):
        coord = self._coord_with_devices(
            [
                DeviceDto(id="speaker-1", image_set_type="dt_boom_r2_dark_blue_s"),
                DeviceDto(id="lamp-1", image_set_type="dt_bulb_e27_m"),
            ]
        )
        with patch(
            "custom_components.sberhome.websocket_api.intents.get_coordinator",
            return_value=coord,
        ):
            ws_devices_for_picker(hass, connection, {"id": 13})
        result = connection.send_result.call_args[0][1]
        assert len(result["devices"]) == 2

    def test_category_list_filter(self, hass, connection):
        coord = self._coord_with_devices(
            [
                DeviceDto(id="speaker-1", image_set_type="dt_boom_r2_dark_blue_s"),
                DeviceDto(id="lamp-1", image_set_type="dt_bulb_e27_m"),
                DeviceDto(id="socket-1", image_set_type="dt_socket"),
            ]
        )
        with patch(
            "custom_components.sberhome.websocket_api.intents.get_coordinator",
            return_value=coord,
        ):
            ws_devices_for_picker(
                hass, connection, {"id": 14, "category": ["sber_speaker", "light"]}
            )
        result = connection.send_result.call_args[0][1]
        ids = {d["device_id"] for d in result["devices"]}
        assert ids == {"speaker-1", "lamp-1"}

    def test_picker_includes_devices_not_in_ha_enabled_set(self, hass, connection):
        """Критическое требование: picker возвращает ВСЕ Sber-устройства,
        даже те, которых нет в HA enabled_device_ids."""
        coord = self._coord_with_devices(
            [
                DeviceDto(
                    id="speaker-not-imported",
                    image_set_type="dt_boom_r2_dark_blue_s",
                ),
            ]
        )
        # enabled_device_ids — пустой set, т.е. ничего не подключено в HA.
        coord.enabled_device_ids = set()
        with patch(
            "custom_components.sberhome.websocket_api.intents.get_coordinator",
            return_value=coord,
        ):
            ws_devices_for_picker(hass, connection, {"id": 15, "category": "sber_speaker"})
        result = connection.send_result.call_args[0][1]
        # Должно вернуть колонку, несмотря на enabled_device_ids=∅.
        assert len(result["devices"]) == 1
        assert result["devices"][0]["device_id"] == "speaker-not-imported"

    def test_no_coordinator(self, hass, connection):
        with patch(
            "custom_components.sberhome.websocket_api.intents.get_coordinator",
            return_value=None,
        ):
            ws_devices_for_picker(hass, connection, {"id": 16})
        assert connection.send_error.call_args[0][1] == "not_loaded"


async def test_regime_save_keeps_neighbors_and_unknown_conditions(hass, connection):
    """Full observed scenario through WS/service; only edited nested commands change."""
    source = json.loads((Path(__file__).parent / "fixtures/scenario_full_example.json").read_text())
    stored = encode_scenario(decode_scenario(source))
    stored["id"] = "test-scenario"
    original = deepcopy(stored)
    coord = MagicMock()
    coord.state_cache.get_homes.return_value = []

    async def get(_path):
        return MagicMock(json=lambda: deepcopy(stored))

    async def put(_path, *, json):
        stored.clear()
        stored.update(deepcopy(json))
        return MagicMock(json=lambda: deepcopy(stored))

    coord.client.transport.get = AsyncMock(side_effect=get)
    coord.client.transport.put = AsyncMock(side_effect=put)
    with _patch_service(IntentService(coord)):
        await ws_get_intent.__wrapped__(hass, connection, {"id": 1, "intent_id": "test-scenario"})
        payload = deepcopy(connection.send_result.call_args.args[1])
        assert payload["is_ha_managed"] is True
        action = next(a for a in payload["actions"] if a["type"] == "regime_command")
        action["data"]["commands"].pop(1)
        action["data"]["commands"][0]["text"] = "Изменённая команда"
        await ws_update_intent.__wrapped__(
            hass, connection, {"id": 2, "intent_id": "test-scenario", "spec": payload}
        )
        await ws_get_intent.__wrapped__(hass, connection, {"id": 3, "intent_id": "test-scenario"})
    connection.send_error.assert_not_called()
    assert connection.send_result.call_args.args[1]["triggers"] == payload["triggers"]
    expected = original["steps"][0]["tasks"]
    regime = next(t for t in expected if t["type"] == "REGIME_COMMAND")
    regime["regime_command_data"]["tasks"].pop(1)
    regime["regime_command_data"]["tasks"][0]["head_dialog_command_task_data"]["text"] = (
        "Изменённая команда"
    )
    assert stored["steps"][0]["tasks"] == expected
    assert stored["steps"][0]["condition"] == original["steps"][0]["condition"]


async def test_condition_group_ws_edit_preserves_other_branches_and_actions(hass, connection):
    source = json.loads((Path(__file__).parent / "fixtures/scenario_full_example.json").read_text())
    stored = encode_scenario(decode_scenario(source))
    stored["id"] = "test-scenario"
    original = deepcopy(stored)
    coord = MagicMock()
    coord.state_cache.get_homes.return_value = []

    async def get(_path):
        return MagicMock(json=lambda: deepcopy(stored))

    async def put(_path, *, json):
        stored.clear()
        stored.update(deepcopy(json))
        return MagicMock(json=lambda: deepcopy(stored))

    coord.client.transport.get = AsyncMock(side_effect=get)
    coord.client.transport.put = AsyncMock(side_effect=put)
    with _patch_service(IntentService(coord)):
        await ws_get_intent.__wrapped__(hass, connection, {"id": 1, "intent_id": "test-scenario"})
        payload = deepcopy(connection.send_result.call_args.args[1])
        node = next(t for t in payload["triggers"] if t["type"] == "group")
        node["data"]["conditions"][1]["data"]["attribute"]["bool_value"] = False
        await ws_update_intent.__wrapped__(
            hass, connection, {"id": 2, "intent_id": "test-scenario", "spec": payload}
        )
        await ws_get_intent.__wrapped__(hass, connection, {"id": 3, "intent_id": "test-scenario"})
    connection.send_error.assert_not_called()
    reopened = connection.send_result.call_args.args[1]
    assert reopened["actions"] == payload["actions"]
    assert stored["steps"][0]["tasks"] == original["steps"][0]["tasks"]
    original["steps"][0]["condition"]["nested_conditions_data"]["conditions"][1][
        "nested_conditions_data"
    ]["conditions"][1]["check_device_conditions_data"]["condition"]["state"]["bool_value"] = False
    assert stored["steps"][0]["condition"] == original["steps"][0]["condition"]
    assert (
        next(t for t in reopened["triggers"] if t["type"] == "group")["data"]["conditions"][1][
            "data"
        ]["attribute"]["bool_value"]
        is False
    )
