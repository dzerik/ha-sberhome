"""Pure unit tests для match_listener — без HA fixtures."""

from custom_components.sberhome.listeners.matcher import EventMeta, match_listener
from custom_components.sberhome.listeners.spec import ListenerFilter, ListenerSpec


def _spec(**kwargs) -> ListenerSpec:
    """Helper: ListenerSpec со всеми обязательными полями + filter."""
    return ListenerSpec(
        slug=kwargs.pop("slug", "test"),
        name=kwargs.pop("name", "Test"),
        filter=ListenerFilter(**kwargs),
    )


def _event(**kwargs) -> EventMeta:
    return EventMeta(
        scenario_id=kwargs.get("scenario_id", "sc-1"),
        scenario_name=kwargs.get("scenario_name", "Доброе утро"),
        trigger_type=kwargs.get("trigger_type", "TIME"),
        home_id=kwargs.get("home_id", "home-1"),
    )


def test_match_trigger_type_single():
    spec = _spec(trigger_types=frozenset({"TIME"}))
    assert match_listener(spec, _event(trigger_type="TIME")) is True
    assert match_listener(spec, _event(trigger_type="PHRASES")) is False


def test_match_trigger_type_list_OR():
    spec = _spec(trigger_types=frozenset({"TIME", "GEO_TIME"}))
    assert match_listener(spec, _event(trigger_type="TIME")) is True
    assert match_listener(spec, _event(trigger_type="GEO_TIME")) is True
    assert match_listener(spec, _event(trigger_type="DEVICE")) is False


def test_match_scenario_name_case_insensitive():
    spec = _spec(scenario_name="Доброе утро")
    assert match_listener(spec, _event(scenario_name="доброе утро")) is True
    assert match_listener(spec, _event(scenario_name="  ДОБРОЕ УТРО  ")) is True
    assert match_listener(spec, _event(scenario_name="Спокойной ночи")) is False


def test_match_scenario_id_exact():
    spec = _spec(scenario_id="abc-123")
    assert match_listener(spec, _event(scenario_id="abc-123")) is True
    assert match_listener(spec, _event(scenario_id="abc-124")) is False


def test_match_home_id_exact():
    spec = _spec(home_id="home-A")
    assert match_listener(spec, _event(home_id="home-A")) is True
    assert match_listener(spec, _event(home_id="home-B")) is False


def test_match_AND_across_fields():
    """Если два поля заданы — оба должны совпасть."""
    spec = _spec(trigger_types=frozenset({"TIME"}), home_id="home-A")
    assert match_listener(spec, _event(trigger_type="TIME", home_id="home-A")) is True
    assert match_listener(spec, _event(trigger_type="TIME", home_id="home-B")) is False
    assert match_listener(spec, _event(trigger_type="PHRASES", home_id="home-A")) is False


def test_match_disabled_always_false():
    spec = ListenerSpec(
        slug="x",
        name="X",
        filter=ListenerFilter(trigger_types=frozenset({"TIME"})),
        enabled=False,
    )
    assert match_listener(spec, _event(trigger_type="TIME")) is False


def test_match_none_field_matches_anything():
    """Filter с trigger_types=None матчит любой trigger_type."""
    spec = _spec(home_id="home-1")  # filter только по home_id
    assert match_listener(spec, _event(trigger_type="TIME")) is True
    assert match_listener(spec, _event(trigger_type="PHRASES")) is True


def test_match_event_with_none_trigger_type():
    """Если event.trigger_type=None — match по trigger_types fails."""
    spec = _spec(trigger_types=frozenset({"TIME"}))
    assert match_listener(spec, _event(trigger_type=None)) is False


def test_match_event_with_none_scenario_name():
    spec = _spec(scenario_name="Test")
    assert match_listener(spec, _event(scenario_name=None)) is False
