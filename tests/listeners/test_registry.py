"""ListenerRegistry tests."""

from custom_components.sberhome.listeners.matcher import EventMeta
from custom_components.sberhome.listeners.registry import ListenerRegistry
from custom_components.sberhome.listeners.spec import ListenerFilter, ListenerSpec


def _spec(slug: str, **filter_kwargs) -> ListenerSpec:
    return ListenerSpec(
        slug=slug,
        name=slug,
        filter=ListenerFilter(**filter_kwargs),
    )


def _evt(**kwargs) -> EventMeta:
    return EventMeta(
        scenario_id=kwargs.get("scenario_id", "sc-1"),
        scenario_name=kwargs.get("scenario_name", "Test"),
        trigger_type=kwargs.get("trigger_type", "TIME"),
        home_id=kwargs.get("home_id", "home-1"),
    )


def test_find_matching_returns_all_matching():
    reg = ListenerRegistry(
        [
            _spec("a", trigger_types=frozenset({"TIME"})),
            _spec("b", trigger_types=frozenset({"PHRASES"})),
            _spec("c", trigger_types=frozenset({"TIME"}), home_id="home-1"),
        ]
    )
    matches = reg.find_matching(_evt(trigger_type="TIME", home_id="home-1"))
    assert {s.slug for s in matches} == {"a", "c"}


def test_find_matching_empty_returns_empty():
    reg = ListenerRegistry([])
    assert reg.find_matching(_evt()) == []


def test_list_returns_all_specs():
    specs = [
        _spec("a", trigger_types=frozenset({"TIME"})),
        _spec("b", trigger_types=frozenset({"PHRASES"})),
    ]
    reg = ListenerRegistry(specs)
    assert reg.list() == specs


def test_mark_fired_updates_last_fired_at():
    reg = ListenerRegistry([_spec("a", trigger_types=frozenset({"TIME"}))])
    spec = reg.list()[0]
    assert spec.last_fired_at is None
    reg.mark_fired(spec, "2026-05-13T08:00:00+00:00")
    assert spec.last_fired_at == "2026-05-13T08:00:00+00:00"


def test_replace_resets_last_fired():
    """После replace новые specs приходят с last_fired_at=None."""
    reg = ListenerRegistry([_spec("a", trigger_types=frozenset({"TIME"}))])
    reg.mark_fired(reg.list()[0], "2026-05-13T08:00:00+00:00")
    new_specs = [_spec("a", trigger_types=frozenset({"TIME"}))]
    reg.replace(new_specs)
    assert reg.list()[0].last_fired_at is None


def test_disabled_listener_not_in_matches():
    """enabled=False listener не возвращается из find_matching."""
    spec = ListenerSpec(
        slug="x",
        name="X",
        filter=ListenerFilter(trigger_types=frozenset({"TIME"})),
        enabled=False,
    )
    reg = ListenerRegistry([spec])
    assert reg.find_matching(_evt(trigger_type="TIME")) == []
