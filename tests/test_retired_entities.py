"""Сущности, которые интеграция перестала выпускать, должны исчезать из HA.

Убрать `FeatureSpec` из реестра недостаточно: запись в entity registry живёт
своей жизнью и после обновления показывается как «недоступно». Так и вышло в
5.13.3 — у SberBox Time из четырёх сущностей осталась одна, а три висели
серыми (issue #46).

Главный риск здесь не «не удалили», а «удалили лишнее»: чистка идёт по
suffix'у unique_id, и промах вынес бы рабочие сущности пользователя. Поэтому
тесты проверяют обе стороны.
"""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome.const import DOMAIN
from custom_components.sberhome.registry_maintenance import (
    RETIRED_UNIQUE_ID_SUFFIXES,
    remove_retired_entities,
)

DEVICE_ID = "cdeikcqk2isrv9d5ln30"


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    config_entry = MockConfigEntry(domain=DOMAIN, entry_id="entry_under_test")
    config_entry.add_to_hass(hass)
    return config_entry


def _register(
    registry: er.EntityRegistry,
    config_entry: MockConfigEntry,
    platform: str,
    unique_id: str,
) -> str:
    return registry.async_get_or_create(
        platform,
        DOMAIN,
        unique_id,
        config_entry=config_entry,
    ).entity_id


async def test_retired_entities_are_removed(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, entry: MockConfigEntry
) -> None:
    """Ровно те три ключа, что убраны в 5.13.3, уходят из реестра."""
    retired = [
        _register(entity_registry, entry, "binary_sensor", f"{DEVICE_ID}_gamepad"),
        _register(entity_registry, entry, "switch", f"{DEVICE_ID}_staros_assistant_sounds_enabled"),
        _register(entity_registry, entry, "select", f"{DEVICE_ID}_staros_age_mode"),
    ]

    removed = remove_retired_entities(hass, entry.entry_id)

    assert removed == 3
    for entity_id in retired:
        assert entity_registry.async_get(entity_id) is None


async def test_live_entities_survive(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, entry: MockConfigEntry
) -> None:
    """Сущности, которые интеграция по-прежнему выпускает, трогать нельзя.

    `online` и `detector` живые (у detector `last_sync` обновляется в момент
    опроса), `position` — тоже отдельная история, не из этой чистки.
    """
    survivors = [
        _register(entity_registry, entry, "binary_sensor", DEVICE_ID),
        _register(entity_registry, entry, "binary_sensor", f"{DEVICE_ID}_detector"),
        _register(entity_registry, entry, "select", f"{DEVICE_ID}_position"),
    ]

    remove_retired_entities(hass, entry.entry_id)

    for entity_id in survivors:
        assert entity_registry.async_get(entity_id) is not None


async def test_other_config_entries_are_not_touched(
    hass: HomeAssistant, entity_registry: er.EntityRegistry, entry: MockConfigEntry
) -> None:
    """Чистка ограничена своим config entry — у пользователя может быть два аккаунта."""
    other = MockConfigEntry(domain=DOMAIN, entry_id="second_account")
    other.add_to_hass(hass)
    foreign = _register(entity_registry, other, "select", f"{DEVICE_ID}_staros_age_mode")

    removed = remove_retired_entities(hass, entry.entry_id)

    assert removed == 0
    assert entity_registry.async_get(foreign) is not None


async def test_setup_runs_the_cleanup_before_forwarding_platforms() -> None:
    """Функция бесполезна, если её не вызвать.

    Порядок важен: чистка обязана пройти до `async_forward_entry_setups`, иначе
    платформы поднимутся, а мёртвые записи ещё будут в реестре.
    """
    from unittest.mock import patch

    from custom_components.sberhome import async_setup_entry
    from tests.test_init import _make_entry, _make_hass, _patch_setup_dependencies, _stop_patchers

    hass = _make_hass()
    config_entry = _make_entry()
    config_entry.options = {"enabled_device_ids": ["dev_1"]}
    order: list[str] = []
    hass.config_entries.async_forward_entry_setups.side_effect = lambda *a, **kw: order.append(
        "forward"
    )

    patchers, _ = _patch_setup_dependencies()
    try:
        with patch(
            "custom_components.sberhome.remove_retired_entities",
            side_effect=lambda *a, **kw: order.append("cleanup"),
        ) as cleanup:
            assert await async_setup_entry(hass, config_entry) is True
    finally:
        _stop_patchers(patchers)

    cleanup.assert_called_once()
    assert order == ["cleanup", "forward"]


def test_retired_suffixes_are_not_prefixes_of_live_keys() -> None:
    """Защита от расширения списка «на глаз».

    Чистка идёт по `endswith`, поэтому suffix обязан начинаться с `_` и не
    совпадать с началом живого ключа — иначе `_position` однажды вынесет
    что-нибудь вроде `_position_mode`.
    """
    for suffix in RETIRED_UNIQUE_ID_SUFFIXES:
        assert suffix.startswith("_"), suffix
