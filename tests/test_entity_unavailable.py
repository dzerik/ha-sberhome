"""Сущности недоступны, когда облако Сбера не отвечает.

Раньше notify-сущности «Sber TTS/TTC» не зависели от координатора и
оставались доступными при недоступном облаке, а сущности сценариев,
присутствия, групп и индикатора проверяли только наличие своих данных — и
показывали последнее известное состояние, пока опрос раз за разом падал.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import EntityPlatform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome import notify as notify_platform
from custom_components.sberhome.aiosber.auth import (
    AuthManager,
    CompanionTokens,
    InMemoryTokenStore,
)
from custom_components.sberhome.aiosber.dto import (
    AttributeValueDto,
    AttributeValueType,
    DeviceDto,
    IndicatorColor,
    IndicatorColors,
)
from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
from custom_components.sberhome.aiosber.dto.union import UnionDto, UnionType
from custom_components.sberhome.aiosber.service.state_cache import StateCache
from custom_components.sberhome.aiosber.transport import HttpTransport
from custom_components.sberhome.api import SberAPI
from custom_components.sberhome.binary_sensor import SberAtHomeBinarySensor
from custom_components.sberhome.button import SberScenarioButton
from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.coordinator import SberHomeCoordinator
from custom_components.sberhome.event import SberScenarioEvent
from custom_components.sberhome.light import SberIndicatorLight
from custom_components.sberhome.notify import SberHomeTtcNotify, SberHomeTtsNotify
from custom_components.sberhome.switch import SberAtHomeSwitch, SberScenarioActiveSwitch
from custom_components.sberhome.switch_groups import SberGroupSwitch

HOME = UnionDto(id="home-1", name="Дом", group_type=UnionType.HOME)

# --- notify в настоящем Home Assistant ----------------------------------------


class _Cloud:
    def __init__(self) -> None:
        self.down = False

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("network is unreachable", request=request)
        return httpx.Response(200, json={"result": []})


@pytest.fixture
def cloud() -> _Cloud:
    return _Cloud()


@pytest.fixture
async def coordinator(hass: HomeAssistant, cloud: _Cloud) -> AsyncIterator[SberHomeCoordinator]:
    entry = MockConfigEntry(domain=DOMAIN, entry_id="entity-unavailable", options={})
    entry.add_to_hass(hass)
    http = httpx.AsyncClient(transport=httpx.MockTransport(cloud))
    store = InMemoryTokenStore(initial=CompanionTokens(access_token="TOK", expires_in=86400))
    auth = AuthManager(http=http, store=store)
    coord = SberHomeCoordinator(
        hass, entry, AsyncMock(spec=SberAPI), HttpTransport(http=http, auth=auth), auth
    )
    for poll in coord._background_polls():
        poll.disabled = True
    coord._start_ws_task = MagicMock()
    yield coord
    await http.aclose()


@pytest.mark.parametrize("notify_cls", [SberHomeTtsNotify, SberHomeTtcNotify])
async def test_notify_state_follows_cloud_availability(
    hass: HomeAssistant,
    coordinator: SberHomeCoordinator,
    cloud: _Cloud,
    notify_cls: type[SberHomeTtsNotify] | type[SberHomeTtcNotify],
) -> None:
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain="notify",
        platform_name=DOMAIN,
        platform=notify_platform,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    homes = patch.object(coordinator.state_cache, "get_homes", return_value=[HOME])
    with homes:
        await coordinator.async_refresh()
        entity = notify_cls(coordinator, MagicMock(), HOME)
        await platform.async_add_entities([entity])
        entity_id = entity.entity_id
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

        cloud.down = True
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

        cloud.down = False
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state != STATE_UNAVAILABLE

    await platform.async_reset()


@pytest.mark.parametrize("notify_cls", [SberHomeTtsNotify, SberHomeTtcNotify])
def test_notify_unavailable_when_home_removed(
    notify_cls: type[SberHomeTtsNotify] | type[SberHomeTtcNotify],
) -> None:
    """Дом удалён в приложении Сбера — отправлять уведомление некуда."""
    coord = MagicMock()
    coord.last_update_success = True
    coord.state_cache.get_homes.return_value = [HOME]
    entity = notify_cls(coord, MagicMock(), HOME)
    assert entity.available is True

    coord.state_cache.get_homes.return_value = []
    assert entity.available is False


# --- прочие сущности не на SberBaseEntity -------------------------------------


def _group_cache() -> StateCache:
    cache = StateCache()
    online = AttributeValueDto(key="online", type=AttributeValueType.BOOL, bool_value=True)
    device = replace(DeviceDto(id="d1", reported_state=[online]), group_ids=["grp-1"])
    cache.update_from_flat(
        homes=[],
        rooms=[],
        groups=[UnionDto(id="grp-1", name="Свет", group_type=UnionType.GROUP)],
        devices=[device],
    )
    return cache


def _coordinator_with_data() -> MagicMock:
    """Координатор, у которого есть данные для каждой сущности ниже."""
    coord = MagicMock()
    coord.last_update_success = True
    coord.scenarios = [ScenarioDto(id="sc-1", name="Сценарий", is_active=True)]
    coord.at_home = {"home-1": True}
    coord.indicator_colors = IndicatorColors(
        default_colors=[], current_colors=[IndicatorColor(id="c1", hue=10)]
    )
    coord.state_cache = _group_cache()
    return coord


ENTITY_FACTORIES: dict[str, Callable[[Any], Any]] = {
    "scenario_button": lambda c: SberScenarioButton(c, "sc-1", "Сценарий"),
    "scenario_active_switch": lambda c: SberScenarioActiveSwitch(c, "sc-1", "Сценарий"),
    "scenario_event": lambda c: SberScenarioEvent(c, "sc-1", "Сценарий"),
    "at_home_binary_sensor": lambda c: SberAtHomeBinarySensor(c, "home-1", "Дом"),
    "at_home_switch": lambda c: SberAtHomeSwitch(c, "home-1", "Дом"),
    "indicator_light": SberIndicatorLight,
    "group_switch": lambda c: SberGroupSwitch(c, "grp-1"),
}


@pytest.mark.parametrize("factory", ENTITY_FACTORIES.values(), ids=ENTITY_FACTORIES.keys())
def test_entity_unavailable_while_cloud_update_fails(factory: Callable[[Any], Any]) -> None:
    coord = _coordinator_with_data()
    entity = factory(coord)
    assert entity.available is True

    coord.last_update_success = False
    assert entity.available is False
