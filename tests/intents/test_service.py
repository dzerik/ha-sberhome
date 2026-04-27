"""IntentService tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.sberhome.aiosber.dto.scenario import ScenarioEventDto
from custom_components.sberhome.aiosber.dto.union import UnionDto
from custom_components.sberhome.intents.service import IntentService
from custom_components.sberhome.intents.spec import IntentAction, IntentSpec


def _build_service(
    *,
    list_response: dict | None = None,
    get_response: dict | None = None,
    create_response: dict | None = None,
    update_response: dict | None = None,
    history: list | None = None,
    home_id: str | None = "home-1",
) -> tuple[IntentService, MagicMock]:
    coord = MagicMock()

    # Transport mock for list/get/create/update/delete
    transport = MagicMock()
    transport.get = AsyncMock()
    transport.post = AsyncMock()
    transport.put = AsyncMock()
    transport.delete = AsyncMock()

    def _resp(payload):
        r = MagicMock()
        r.json = MagicMock(return_value=payload)
        return r

    if list_response is not None:
        transport.get.return_value = _resp(list_response)
    if create_response is not None:
        transport.post.return_value = _resp(create_response)
    if update_response is not None:
        transport.put.return_value = _resp(update_response)

    coord.home_api = MagicMock()
    coord.home_api._transport = transport

    # client.scenarios.history for last_fired_at
    coord.client = MagicMock()
    coord.client.scenarios = MagicMock()
    coord.client.scenarios.history = AsyncMock(return_value=history or [])
    coord.client.scenarios.execute_command = AsyncMock(return_value={"ok": True})

    coord.state_cache = MagicMock()
    if home_id:
        coord.state_cache.get_home = MagicMock(return_value=UnionDto(id=home_id))
    else:
        coord.state_cache.get_home = MagicMock(return_value=None)

    return IntentService(coord), coord


SAMPLE_SCENARIO = {
    "id": "sc-1",
    "name": "Утро",
    "is_active": True,
    "image": "https://...",
    "steps": [
        {
            "tasks": [
                {
                    "type": "PRONOUNCE_COMMAND",
                    "pronounce_data": {"phrase": "Доброе утро", "device_ids": ["s-1"]},
                }
            ],
            "condition": {
                "type": "PHRASES",
                "phrases_data": {"phrases": ["доброе утро"]},
            },
        }
    ],
}


class TestListIntents:
    @pytest.mark.asyncio
    async def test_returns_specs_with_last_fired_at(self):
        history = [
            ScenarioEventDto(
                id="e1",
                event_time="2026-04-27T13:00:00Z",
                object_id="sc-1",
                type="SUCCESS",
            )
        ]
        service, coord = _build_service(
            list_response={"scenarios": [SAMPLE_SCENARIO], "pagination": {}},
            history=history,
        )
        specs = await service.list_intents()
        assert len(specs) == 1
        assert specs[0].id == "sc-1"
        assert specs[0].name == "Утро"
        assert specs[0].last_fired_at == "2026-04-27T13:00:00Z"

    @pytest.mark.asyncio
    async def test_no_home_id_skips_last_fired_at(self):
        service, _ = _build_service(
            list_response={"scenarios": [SAMPLE_SCENARIO], "pagination": {}},
            home_id=None,
        )
        specs = await service.list_intents()
        assert specs[0].last_fired_at is None

    @pytest.mark.asyncio
    async def test_history_failure_does_not_break_list(self):
        service, coord = _build_service(
            list_response={"scenarios": [SAMPLE_SCENARIO], "pagination": {}},
        )
        coord.client.scenarios.history.side_effect = RuntimeError("boom")
        # list_intents должен переварить ошибку history без exception'а наружу.
        specs = await service.list_intents()
        assert len(specs) == 1
        assert specs[0].last_fired_at is None


class TestGetIntent:
    @pytest.mark.asyncio
    async def test_known_id_returns_spec(self):
        service, _ = _build_service(list_response={"result": SAMPLE_SCENARIO})
        spec = await service.get_intent("sc-1")
        assert spec is not None
        assert spec.id == "sc-1"

    @pytest.mark.asyncio
    async def test_missing_returns_none(self):
        service, _ = _build_service(list_response={})
        assert await service.get_intent("nope") is None


class TestCreateIntent:
    @pytest.mark.asyncio
    async def test_creates_and_returns_id(self):
        service, coord = _build_service(
            create_response={"result": {**SAMPLE_SCENARIO, "id": "new-id"}},
        )
        spec = IntentSpec(
            name="X",
            phrases=["x"],
            actions=[IntentAction(type="ha_event_only")],
        )
        result = await service.create_intent(spec)
        assert result.id == "new-id"
        # Проверяем что body не содержит id (POST без id).
        body = coord.home_api._transport.post.await_args[1]["json"]
        assert "id" not in body

    @pytest.mark.asyncio
    async def test_post_endpoint_used(self):
        service, coord = _build_service(create_response={"result": SAMPLE_SCENARIO})
        await service.create_intent(IntentSpec(name="X", phrases=["x"]))
        path = coord.home_api._transport.post.await_args[0][0]
        assert path == "/scenario/v2/scenario"


class TestUpdateIntent:
    @pytest.mark.asyncio
    async def test_put_includes_id_in_body(self):
        service, coord = _build_service(
            update_response={"result": SAMPLE_SCENARIO},
        )
        spec = IntentSpec(
            id="sc-1",
            name="Renamed",
            phrases=["x"],
            raw_extras={"image": "https://..."},
        )
        await service.update_intent("sc-1", spec)
        body = coord.home_api._transport.put.await_args[1]["json"]
        assert body["id"] == "sc-1"
        assert body["name"] == "Renamed"


class TestDeleteIntent:
    @pytest.mark.asyncio
    async def test_calls_delete_endpoint(self):
        service, coord = _build_service()
        await service.delete_intent("sc-99")
        path = coord.home_api._transport.delete.await_args[0][0]
        assert path == "/scenario/v2/scenario/sc-99"


class TestTestIntent:
    """Test now = fire HA event simulation (Sber API не даёт programmatic-run)."""

    @pytest.mark.asyncio
    async def test_fires_ha_event_with_metadata(self):
        service, coord = _build_service(list_response={"result": SAMPLE_SCENARIO})
        # hass.bus mock — чтобы тестировать что fire'ится правильный event.
        coord.hass = MagicMock()
        coord.hass.bus = MagicMock()
        coord.hass.bus.async_fire = MagicMock()

        result = await service.test_intent("sc-1")
        assert result["ok"] is True
        assert result["simulated"] is True

        # HA event fired с правильным event type.
        from custom_components.sberhome.coordinator import EVENT_SBERHOME_INTENT

        coord.hass.bus.async_fire.assert_called_once()
        call = coord.hass.bus.async_fire.call_args
        assert call[0][0] == EVENT_SBERHOME_INTENT
        data = call[0][1]
        assert data["name"] == "Утро"
        assert data["scenario_id"] == "sc-1"
        assert data["simulated"] is True
        assert "event_time" in data
        assert data["type"] == "SUCCESS"

    @pytest.mark.asyncio
    async def test_does_not_call_sber_command_endpoint(self):
        """Critical: НЕ дёргает Sber API — это симуляция, не real execute."""
        service, coord = _build_service(list_response={"result": SAMPLE_SCENARIO})
        coord.hass = MagicMock()
        coord.hass.bus = MagicMock()
        coord.hass.bus.async_fire = MagicMock()

        await service.test_intent("sc-1")
        coord.client.scenarios.execute_command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_intent_raises(self):
        service, _ = _build_service(list_response={})
        with pytest.raises(ValueError, match="not found"):
            await service.test_intent("missing")
