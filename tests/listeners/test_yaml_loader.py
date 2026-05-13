"""Listeners YAML loader tests."""

import pytest

from custom_components.sberhome.listeners.spec import (
    ListenerFilter,
    ListenerSpec,
)
from custom_components.sberhome.listeners.yaml_loader import (
    LISTENERS_SCHEMA,
    load_listeners_from_config,
)


def test_listener_filter_construct_all_optional():
    """ListenerFilter без полей валидно (matcher гарантирует ≥1 в YAML loader)."""
    f = ListenerFilter()
    assert f.trigger_types is None
    assert f.scenario_name is None
    assert f.scenario_id is None
    assert f.home_id is None


def test_listener_filter_with_fields():
    f = ListenerFilter(
        trigger_types=frozenset({"TIME"}),
        scenario_name="Доброе утро",
        scenario_id="abc-123",
        home_id="home-1",
    )
    assert f.trigger_types == frozenset({"TIME"})
    assert f.scenario_name == "Доброе утро"


def test_listener_spec_construct():
    spec = ListenerSpec(
        slug="morning",
        name="Утренние сценарии",
        filter=ListenerFilter(trigger_types=frozenset({"TIME"})),
        enabled=True,
        description="по расписанию",
    )
    assert spec.slug == "morning"
    assert spec.enabled is True
    assert spec.filter.trigger_types == frozenset({"TIME"})


def test_load_minimal_listener():
    raw = LISTENERS_SCHEMA(
        [
            {
                "slug": "any_time",
                "name": "Любые time-сценарии",
                "filter": {"trigger_type": "TIME"},
            }
        ]
    )
    specs = load_listeners_from_config(raw, reserved_slugs=set())
    assert len(specs) == 1
    s = specs[0]
    assert s.slug == "any_time"
    assert s.name == "Любые time-сценарии"
    assert s.filter.trigger_types == frozenset({"TIME"})
    assert s.enabled is True


def test_load_filter_trigger_type_list():
    raw = LISTENERS_SCHEMA(
        [
            {
                "slug": "morning",
                "name": "Morning",
                "filter": {"trigger_type": ["TIME", "GEO_TIME"]},
            }
        ]
    )
    specs = load_listeners_from_config(raw, reserved_slugs=set())
    assert specs[0].filter.trigger_types == frozenset({"TIME", "GEO_TIME"})


def test_load_slug_autogen_from_cyrillic_name():
    raw = LISTENERS_SCHEMA(
        [
            {
                "name": "Доброе утро",
                "filter": {"trigger_type": "TIME"},
            }
        ]
    )
    specs = load_listeners_from_config(raw, reserved_slugs=set())
    assert specs[0].slug == "dobroe_utro"


def test_load_empty_filter_invalid():
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        LISTENERS_SCHEMA([{"slug": "x", "name": "X", "filter": {}}])


def test_load_unknown_trigger_type_invalid():
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        LISTENERS_SCHEMA(
            [
                {
                    "slug": "x",
                    "name": "X",
                    "filter": {"trigger_type": "FOO_BAR"},
                }
            ]
        )


def test_load_duplicate_slug_within_listeners_raises():
    raw = LISTENERS_SCHEMA(
        [
            {"slug": "dup", "name": "A", "filter": {"trigger_type": "TIME"}},
            {"slug": "dup", "name": "B", "filter": {"trigger_type": "TIME"}},
        ]
    )
    with pytest.raises(ValueError, match="duplicate slug"):
        load_listeners_from_config(raw, reserved_slugs=set())


def test_load_collision_with_intent_slug_disables_listener(caplog):
    """Listener со slug, который зарезервирован intent'ом — disabled, warning."""
    raw = LISTENERS_SCHEMA(
        [
            {"slug": "morning", "name": "X", "filter": {"trigger_type": "TIME"}},
            {"slug": "evening", "name": "Y", "filter": {"trigger_type": "TIME"}},
        ]
    )
    with caplog.at_level("WARNING"):
        specs = load_listeners_from_config(raw, reserved_slugs={"morning"})
    by_slug = {s.slug: s for s in specs}
    assert by_slug["morning"].enabled is False
    assert by_slug["evening"].enabled is True
    assert any("morning" in r.message and "reserved" in r.message.lower() for r in caplog.records)


def test_load_enabled_false_parsed():
    raw = LISTENERS_SCHEMA(
        [
            {
                "slug": "x",
                "name": "X",
                "enabled": False,
                "filter": {"trigger_type": "TIME"},
            }
        ]
    )
    specs = load_listeners_from_config(raw, reserved_slugs=set())
    assert specs[0].enabled is False
