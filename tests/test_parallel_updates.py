"""Сколько команд одной платформы Home Assistant отправляет в облако Сбера сразу.

Платформы, чьи сущности только читают данные координатора, не ограничиваются.
Платформы с командами ограничены одной одновременной командой: облако одно на
весь аккаунт и на всплеск запросов отвечает 429. Проверяется, как Home
Assistant на деле применяет константу модуля платформы к вызовам сущностей.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
from datetime import timedelta

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import EntityPlatform

from custom_components.sberhome import PLATFORMS
from custom_components.sberhome.const import DOMAIN

READ_ONLY_PLATFORMS = frozenset(
    {Platform.BINARY_SENSOR, Platform.EVENT, Platform.SENSOR, Platform.UPDATE}
)
"""Платформы без действий, уходящих в облако."""


class _Probe(Entity):
    _attr_should_poll = False

    def __init__(self, name: str) -> None:
        self._attr_unique_id = name
        self._attr_name = name


async def _max_concurrent_calls(hass: HomeAssistant, platform: Platform) -> int:
    """Запустить по вызову на трёх сущностях платформы сразу и вернуть пик параллельности."""
    entity_platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain=platform.value,
        platform_name=DOMAIN,
        platform=importlib.import_module(f"custom_components.sberhome.{platform.value}"),
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    probes = [_Probe(f"probe_{platform.value}_{i}") for i in range(3)]
    await entity_platform.async_add_entities(probes)

    running = 0
    peak = 0

    async def command() -> None:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1

    await asyncio.gather(*(probe.async_request_call(command()) for probe in probes))
    await entity_platform.async_reset()
    return peak


@pytest.mark.parametrize("platform", PLATFORMS, ids=lambda p: p.value)
async def test_platform_parallelism(hass: HomeAssistant, platform: Platform) -> None:
    expected = 3 if platform in READ_ONLY_PLATFORMS else 1
    assert await _max_concurrent_calls(hass, platform) == expected


@pytest.mark.parametrize("platform", PLATFORMS, ids=lambda p: p.value)
def test_platform_declares_parallel_updates(platform: Platform) -> None:
    """Значение задано явно, а не выведено Home Assistant по умолчанию."""
    module = importlib.import_module(f"custom_components.sberhome.{platform.value}")
    expected = 0 if platform in READ_ONLY_PLATFORMS else 1
    declared = module.PARALLEL_UPDATES
    assert declared == expected
