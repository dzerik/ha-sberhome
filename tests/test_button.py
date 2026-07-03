"""Tests for SberHome button platform — sbermap-driven (PR #7 + PR #9).

Два вида кнопок:
- SberSbermapButton — fire-and-forget действия устройства (intercom unlock).
- SberScenarioButton — виртуальная кнопка запуска Sber-сценария,
  группируется в service-device (DOMAIN, "scenarios").
"""

from __future__ import annotations

import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.const import EntityCategory

from custom_components.sberhome.aiosber.dto import AttributeValueType
from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.button import (
    SberSbermapButton,
    SberScenarioButton,
    async_setup_entry,
)
from custom_components.sberhome.const import DOMAIN

from .conftest import MOCK_DEVICE_INTERCOM, build_coordinator_caches


def _intercom_raw() -> dict:
    """Intercom с action-ключами unlock/reject_call в reported_state."""
    raw = copy.deepcopy(MOCK_DEVICE_INTERCOM)
    raw["reported_state"] += [
        {"key": "unlock", "bool_value": False},
        {"key": "reject_call", "bool_value": False},
    ]
    return raw


def _coord_with_raw(raw_devices: dict[str, dict]) -> MagicMock:
    """Coordinator-mock: DTO + sbermap entities + StateCache из raw-словарей."""
    coord = MagicMock()
    coord.devices, coord.entities = build_coordinator_caches(raw_devices)
    cache = StateCache()
    cache.update_from_devices(coord.devices)
    coord.state_cache = cache
    coord.async_send_device_state = AsyncMock()
    coord.async_execute_scenario = AsyncMock()
    coord.scenarios = []
    return coord


class TestSbermapButton:
    @pytest.fixture
    def coord(self) -> MagicMock:
        return _coord_with_raw({"device_intercom_1": _intercom_raw()})

    @pytest.fixture
    def entity(self, coord) -> SberSbermapButton:
        ent = next(
            e
            for e in coord.entities["device_intercom_1"]
            if e.unique_id == "device_intercom_1_unlock"
        )
        return SberSbermapButton(coord, "device_intercom_1", ent)

    def test_unique_id_has_action_suffix(self, entity):
        """unique_id = <device_id>_<action_key>."""
        assert entity.unique_id == "device_intercom_1_unlock"

    def test_icon_from_feature_spec(self, entity):
        """Иконка открытой двери из FeatureSpec intercom.unlock."""
        assert entity.icon == "mdi:door-open"

    @pytest.mark.asyncio
    async def test_press_sends_unlock_command(self, coord, entity):
        """press → команда unlock=true (BOOL) на устройство."""
        await entity.async_press()
        coord.async_send_device_state.assert_awaited_once()
        device_id, attrs = coord.async_send_device_state.await_args.args
        assert device_id == "device_intercom_1"
        assert len(attrs) == 1
        assert attrs[0].key == "unlock"
        assert attrs[0].type is AttributeValueType.BOOL
        assert attrs[0].bool_value is True


class TestScenarioButton:
    @pytest.fixture
    def coord(self) -> MagicMock:
        coord = MagicMock()
        coord.scenarios = [
            ScenarioDto(id="scn-1", name="Доброе утро"),
            ScenarioDto(id="scn-2", name="Уход из дома"),
        ]
        coord.async_execute_scenario = AsyncMock()
        return coord

    @pytest.fixture
    def entity(self, coord) -> SberScenarioButton:
        return SberScenarioButton(coord, "scn-1", "Доброе утро")

    def test_unique_id(self, entity):
        """unique_id стабильно завязан на scenario_id."""
        assert entity.unique_id == "sberhome_scenario_scn-1"

    def test_name_is_scenario_name(self, entity):
        """Имя entity — человекочитаемое имя сценария."""
        assert entity.name == "Доброе утро"

    def test_device_info_scenarios_service(self, entity):
        """Кнопки собраны в один virtual device (DOMAIN, 'scenarios')."""
        info = entity.device_info
        assert (DOMAIN, "scenarios") in info["identifiers"]
        assert info["entry_type"] == "service"

    def test_entity_category_config(self, entity):
        """Scenario-кнопки — config, не primary controls."""
        assert entity.entity_category is EntityCategory.CONFIG

    def test_available_while_scenario_exists(self, entity):
        """Сценарий присутствует в coordinator.scenarios → available."""
        assert entity.available is True

    def test_unavailable_when_scenario_removed(self, coord, entity):
        """Сценарий удалён на стороне Sber → available False."""
        coord.scenarios = [ScenarioDto(id="scn-2", name="Уход из дома")]
        assert entity.available is False

    @pytest.mark.asyncio
    async def test_press_executes_scenario(self, coord, entity):
        """press → coordinator.async_execute_scenario(<scenario_id>)."""
        await entity.async_press()
        coord.async_execute_scenario.assert_awaited_once_with("scn-1")


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_device_and_scenario_buttons(self):
        """Setup: 2 intercom-кнопки + по кнопке на валидный сценарий."""
        coord = _coord_with_raw({"device_intercom_1": _intercom_raw()})
        coord.scenarios = [
            ScenarioDto(id="scn-1", name="Доброе утро"),
            ScenarioDto(id=None, name="Без id — пропустить"),
            ScenarioDto(id="scn-3", name=None),
        ]
        entry = MagicMock()
        entry.runtime_data = coord
        captured: list = []
        await async_setup_entry(MagicMock(), entry, captured.extend)

        sbermap = [e for e in captured if isinstance(e, SberSbermapButton)]
        scenario = [e for e in captured if isinstance(e, SberScenarioButton)]
        assert {b.unique_id for b in sbermap} == {
            "device_intercom_1_unlock",
            "device_intercom_1_reject_call",
        }
        # Сценарии без id или name отфильтрованы.
        assert [b.unique_id for b in scenario] == ["sberhome_scenario_scn-1"]
