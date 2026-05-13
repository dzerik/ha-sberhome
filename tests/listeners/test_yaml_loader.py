"""Listeners YAML loader tests."""

from custom_components.sberhome.listeners.spec import (
    ListenerFilter,
    ListenerSpec,
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
