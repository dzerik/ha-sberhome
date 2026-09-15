"""Права сервисов SberHome и ошибки действий сущностей.

До исправления:

- ``sberhome.send_raw_command`` (PUT произвольного состояния любого устройства
  аккаунта) и ``sberhome.reload_intents`` (создание/изменение облачных
  сценариев) мог вызвать любой пользователь Home Assistant, а
  ``send_raw_command`` подставлял device_id в путь запроса без проверки;
- ошибка авторизации в действии сущности поднимала ``ConfigEntryAuthFailed``,
  который вне настройки записи повторный вход не запускает, а прочие ошибки
  облака уходили наружу как есть — с английским текстом и URL запросов.

Проверки идут через настоящий реестр сервисов и настоящие записи HA.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError, Unauthorized
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome import (
    RAW_STATE_MAX_BYTES,
    RAW_STATE_MAX_ITEMS,
    _async_register_services,
)
from custom_components.sberhome.aiosber.dto.values import AttributeValueDto, AttributeValueType
from custom_components.sberhome.aiosber.exceptions import (
    ApiError,
    AuthError,
    InvalidGrant,
    NetworkError,
    ProtocolError,
    RateLimitError,
    RequestUnauthorized,
)
from custom_components.sberhome.const import CONF_AUTH_METHOD, CONF_TOKEN, DOMAIN
from custom_components.sberhome.entity import SberBaseEntity

from .conftest import MOCK_DEVICE_LIGHT
from .test_entity import _make_coordinator

_SECRET = "access_token=very-secret-value"
"""Фрагмент, который не должен попасть в сообщение пользователю."""

_VALID_STATE = [{"key": "on_off", "type": "BOOL", "bool_value": True}]


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Дать загрузчику HA найти ``custom_components/sberhome`` (и при editable-установке)."""
    import custom_components

    real_dirs = [p for p in dict.fromkeys(custom_components.__path__) if Path(p).is_dir()]
    monkeypatch.setattr(custom_components, "__path__", real_dirs)


async def _context(hass: HomeAssistant, *, admin: bool) -> Context:
    if not await hass.auth.async_get_users():
        # Первый созданный пользователь становится владельцем, а владелец — админ.
        await hass.auth.async_create_user("owner", group_ids=["system-admin"])
    group = "system-admin" if admin else "system-users"
    user = await hass.auth.async_create_user("tester", group_ids=[group])
    assert user.is_admin is admin
    return Context(user_id=user.id)


# --- права сервисов ------------------------------------------------------------


@pytest.fixture
def loaded_coordinator(hass: HomeAssistant) -> Iterator[MagicMock]:
    """Загруженная запись с координатором-заглушкой; сеть не используется."""
    coord = MagicMock()
    coord.client.transport.put = AsyncMock()
    coord.async_refresh = AsyncMock()
    coord.last_update_success = True
    coord.async_refresh_staros = AsyncMock()
    coord.state_cache.get_homes.return_value = [MagicMock(id="H1")]
    coord.tts_service.send = AsyncMock()
    coord.ttc_service.send = AsyncMock()
    entry = MagicMock()
    entry.runtime_data = coord
    with patch.object(hass.config_entries, "async_loaded_entries", return_value=[entry]):
        yield coord


@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("send_raw_command", {"device_id": "abc123", "state": _VALID_STATE}),
        ("reload_intents", {}),
    ],
)
async def test_admin_services_reject_non_admin(
    hass: HomeAssistant, loaded_coordinator: MagicMock, service: str, data: dict[str, Any]
) -> None:
    _async_register_services(hass)
    context = await _context(hass, admin=False)

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN, service, data, blocking=True, context=context, return_response=True
        )
    loaded_coordinator.client.transport.put.assert_not_awaited()


async def test_send_raw_command_allowed_for_admin(
    hass: HomeAssistant, loaded_coordinator: MagicMock
) -> None:
    _async_register_services(hass)
    context = await _context(hass, admin=True)

    result = await hass.services.async_call(
        DOMAIN,
        "send_raw_command",
        {"device_id": "69ef56e968370bebf006ce7a", "state": _VALID_STATE},
        blocking=True,
        context=context,
        return_response=True,
    )

    assert result is not None and result["ok"] is True
    put = loaded_coordinator.client.transport.put
    put.assert_awaited_once()
    assert put.await_args.args[0] == "/devices/69ef56e968370bebf006ce7a/state"
    assert put.await_args.kwargs["json"]["desired_state"] == _VALID_STATE


@pytest.mark.parametrize("service", ["refresh", "tts_send", "ttc_send"])
async def test_non_mutating_or_entity_equivalent_services_stay_open(
    hass: HomeAssistant, loaded_coordinator: MagicMock, service: str
) -> None:
    """refresh только опрашивает, tts/ttc дублируют notify-сущности — прав админа не требуют."""
    _async_register_services(hass)
    context = await _context(hass, admin=False)
    data = {"message": "hi"} if service != "refresh" else {}

    result = await hass.services.async_call(
        DOMAIN, service, data, blocking=True, context=context, return_response=True
    )

    assert result is not None


# --- валидация send_raw_command ------------------------------------------------


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({"device_id": "../scenario/v2/scenario/x", "state": _VALID_STATE}, id="path"),
        pytest.param({"device_id": "abc?x=1", "state": _VALID_STATE}, id="query"),
        pytest.param({"device_id": "", "state": _VALID_STATE}, id="empty-id"),
        pytest.param({"device_id": "a" * 200, "state": _VALID_STATE}, id="long-id"),
        pytest.param({"device_id": "abc", "state": []}, id="empty-state"),
        pytest.param({"device_id": "abc", "state": {"key": "on_off"}}, id="not-list"),
        pytest.param({"device_id": "abc", "state": ["on_off"]}, id="item-not-object"),
        pytest.param({"device_id": "abc", "state": [{"type": "BOOL"}]}, id="no-key"),
        pytest.param({"device_id": "abc", "state": "[{not json"}, id="bad-json-string"),
        pytest.param(
            {
                "device_id": "abc",
                "state": [{"key": f"k{i}"} for i in range(RAW_STATE_MAX_ITEMS + 1)],
            },
            id="too-many",
        ),
        pytest.param(
            {
                "device_id": "abc",
                "state": [{"key": "k", "string_value": "x" * RAW_STATE_MAX_BYTES}],
            },
            id="too-big",
        ),
        pytest.param(
            {"device_id": "abc", "state": [{"key": "k", "float_value": float("nan")}]},
            id="nan",
        ),
    ],
)
async def test_send_raw_command_rejects_invalid_payload(
    hass: HomeAssistant, loaded_coordinator: MagicMock, data: dict[str, Any]
) -> None:
    _async_register_services(hass)
    context = await _context(hass, admin=True)

    with pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN, "send_raw_command", data, blocking=True, context=context, return_response=True
        )
    loaded_coordinator.client.transport.put.assert_not_awaited()


async def test_send_raw_command_accepts_json_string(
    hass: HomeAssistant, loaded_coordinator: MagicMock
) -> None:
    _async_register_services(hass)
    context = await _context(hass, admin=True)

    await hass.services.async_call(
        DOMAIN,
        "send_raw_command",
        {"device_id": "abc-123_x", "state": '[{"key": "on_off", "bool_value": false}]'},
        blocking=True,
        context=context,
        return_response=True,
    )

    put = loaded_coordinator.client.transport.put
    assert put.await_args.kwargs["json"]["desired_state"] == [
        {"key": "on_off", "bool_value": False}
    ]


# --- ошибки действий сущностей -------------------------------------------------


def _attrs() -> list[AttributeValueDto]:
    return [AttributeValueDto(key="on_off", type=AttributeValueType.BOOL, bool_value=True)]


def _entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_AUTH_METHOD: "sberid", CONF_TOKEN: {"access_token": "old"}},
    )
    entry.add_to_hass(hass)
    return entry


def _entity(hass: HomeAssistant, entry: MockConfigEntry, error: Exception) -> SberBaseEntity:
    coordinator = _make_coordinator({"device_light_1": MOCK_DEVICE_LIGHT})
    coordinator.hass = hass
    coordinator.config_entry = entry
    coordinator.async_send_device_state = AsyncMock(side_effect=error)
    return SberBaseEntity(coordinator, "device_light_1")


@pytest.mark.parametrize("error", [AuthError(_SECRET), InvalidGrant(_SECRET)])
async def test_entity_auth_failure_starts_reauth_and_raises_translated(
    hass: HomeAssistant, error: Exception
) -> None:
    entry = _entry(hass)
    entity = _entity(hass, entry, error)

    with pytest.raises(HomeAssistantError) as exc_info:
        await entity._async_send_attrs(_attrs())
    await hass.async_block_till_done()

    err = exc_info.value
    assert err.translation_domain == DOMAIN
    assert err.translation_key == "auth_failed"
    assert _SECRET not in str(err)
    assert len(list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))) == 1


@pytest.mark.parametrize(
    ("error", "key", "exc_type"),
    [
        (NetworkError(_SECRET), "cloud_unreachable", HomeAssistantError),
        (RateLimitError(_SECRET, retry_after=30), "rate_limited", HomeAssistantError),
        (ApiError(500, _SECRET), "api_error", HomeAssistantError),
        (ApiError(400, _SECRET), "command_rejected", ServiceValidationError),
        (ProtocolError(_SECRET), "cloud_error", HomeAssistantError),
    ],
)
async def test_entity_other_cloud_errors_are_translated(
    hass: HomeAssistant, error: Exception, key: str, exc_type: type[HomeAssistantError]
) -> None:
    entry = _entry(hass)
    entity = _entity(hass, entry, error)

    with pytest.raises(exc_type) as exc_info:
        await entity._async_send_attrs(_attrs())
    await hass.async_block_till_done()

    err = exc_info.value
    assert err.translation_domain == DOMAIN
    assert err.translation_key == key
    assert _SECRET not in str(err)
    assert list(entry.async_get_active_flows(hass, {SOURCE_REAUTH})) == []


async def test_non_cloud_errors_are_not_masked(hass: HomeAssistant) -> None:
    """Ошибка в самом коде интеграции остаётся видна как есть, а не «ошибка облака»."""
    entity = _entity(hass, _entry(hass), KeyError("bug"))

    with pytest.raises(KeyError):
        await entity._async_send_attrs(_attrs())


def _direct_cloud_actions(coordinator: MagicMock) -> list[tuple[str, Any]]:
    """Действия сущностей, которые ходят в облако мимо `_async_send_attrs`."""
    from custom_components.sberhome.aiosber.dto import IndicatorColor
    from custom_components.sberhome.button import SberScenarioButton
    from custom_components.sberhome.light import SberIndicatorLight
    from custom_components.sberhome.notify import SberHomeTtcNotify, SberHomeTtsNotify
    from custom_components.sberhome.switch import (
        SberAtHomeSwitch,
        SberScenarioActiveSwitch,
        SberStarosSettingSwitch,
    )
    from custom_components.sberhome.switch_groups import SberGroupSwitch

    home = MagicMock(id="H1")
    home.name = "Дом"
    coordinator.indicator_colors.current_colors = [
        IndicatorColor(id="c1", hue=10, saturation=20, brightness=30)
    ]
    spec = MagicMock(serial="SN", product="sberboom", node_id="n", node_type="BOOL")
    spec.name = "Setting"
    tts = SberHomeTtsNotify(coordinator, coordinator.tts_service, home)
    ttc = SberHomeTtcNotify(coordinator, coordinator.ttc_service, home)

    return [
        ("scenario_button", SberScenarioButton(coordinator, "s1", "S").async_press),
        ("at_home", SberAtHomeSwitch(coordinator, "H1", "Дом").async_turn_on),
        ("scenario_active", SberScenarioActiveSwitch(coordinator, "s1", "S").async_turn_off),
        ("staros_setting", SberStarosSettingSwitch(coordinator, spec).async_turn_on),
        ("indicator", SberIndicatorLight(coordinator).async_turn_off),
        ("tts_notify", lambda: tts.async_send_message("hi")),
        ("ttc_notify", lambda: ttc.async_send_message("hi")),
        ("group_switch", SberGroupSwitch(coordinator, "g1").async_turn_on),
    ]


def _cloud_coordinator(hass: HomeAssistant, entry: MockConfigEntry, error: Exception) -> MagicMock:
    """Координатор-заглушка, у которого каждое обращение к облаку падает с ``error``."""
    coordinator = MagicMock()
    coordinator.hass = hass
    coordinator.config_entry = entry
    coordinator.async_request_refresh = AsyncMock()
    coordinator.async_refresh_scenarios = AsyncMock()
    for name in (
        "async_execute_scenario",
        "async_set_at_home",
        "async_set_scenario_active",
        "async_set_staros_setting",
        "async_set_indicator_color",
    ):
        setattr(coordinator, name, AsyncMock(side_effect=error))
    coordinator.tts_service.send = AsyncMock(side_effect=error)
    coordinator.ttc_service.send = AsyncMock(side_effect=error)
    coordinator.client.groups.set_state = AsyncMock(side_effect=error)
    return coordinator


async def test_direct_cloud_entity_actions_translate_auth_failure(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    coordinator = _cloud_coordinator(hass, entry, AuthError(_SECRET))

    for name, action in _direct_cloud_actions(coordinator):
        with pytest.raises(HomeAssistantError) as exc_info:
            await action()
        assert exc_info.value.translation_key == "auth_failed", name
        assert _SECRET not in str(exc_info.value), name
    await hass.async_block_till_done()
    assert len(list(entry.async_get_active_flows(hass, {SOURCE_REAUTH}))) == 1


async def test_direct_cloud_actions_denied_object_does_not_start_reauth(
    hass: HomeAssistant,
) -> None:
    """401 после успешного refresh (удалённый сценарий) — не повод для повторного входа.

    Раньше нажатие кнопки сценария, удалённого в приложении «Салют!», создавало
    ложный запрос на повторный вход и сообщение «облако не приняло данные
    входа». Теперь — «нет доступа к объекту» и внеочередной опрос, который
    сам решит, нужен ли повторный вход.
    """
    entry = _entry(hass)
    error = RequestUnauthorized("Unauthorized after refresh: POST /scenario/v2/scenario/x/run")
    coordinator = _cloud_coordinator(hass, entry, error)

    actions = _direct_cloud_actions(coordinator)
    for name, action in actions:
        with pytest.raises(HomeAssistantError) as exc_info:
            await action()
        assert exc_info.value.translation_key == "access_denied", name
        assert "/scenario/" not in str(exc_info.value), name
    await hass.async_block_till_done()

    assert list(entry.async_get_active_flows(hass, {SOURCE_REAUTH})) == []
    assert coordinator.async_request_refresh.await_count == len(actions)
    # Сценарии и «я дома» перечитываются сразу только для их собственных действий.
    assert coordinator.async_refresh_scenarios.await_count == len(_SCENARIO_ACTIONS)


_SCENARIO_ACTIONS = ("scenario_button", "at_home", "scenario_active")
"""Действия из ``_direct_cloud_actions``, адресованные сценарию или дому."""


def _scenario_coordinator(
    hass: HomeAssistant, entry: MockConfigEntry, *, poll_disabled: bool
) -> tuple[MagicMock, MagicMock]:
    """Координатор с настоящим опросом сценариев поверх заглушки ScenarioAPI.

    В облаке сценария ``s1`` и дома ``H1`` уже нет: запуск, переключение и
    запись «я дома» отвечают 401 после refresh, список сценариев пуст, а
    чтение «я дома» падает. Внеочередной опрос координатора, как и настоящий
    ``_async_update_data``, опрашивает сценарии только через throttled poll.
    """
    import time

    from custom_components.sberhome.aiosber.dto.scenario import ScenarioDto
    from custom_components.sberhome.coordinator import SberHomeCoordinator, ThrottledPoll

    denied = RequestUnauthorized("Unauthorized after refresh: POST /scenario/v2/scenario/s1/run")
    api = MagicMock()
    api.run = AsyncMock(side_effect=denied)
    api.set_active = AsyncMock(side_effect=denied)
    api.set_at_home = AsyncMock(side_effect=denied)
    api.list = AsyncMock(return_value=[])
    api.get_at_home = AsyncMock(side_effect=RequestUnauthorized("Unauthorized after refresh"))

    coord = MagicMock(spec=SberHomeCoordinator)
    coord.hass = hass
    coord.config_entry = entry
    coord.data = {}
    coord.scenarios = [ScenarioDto(id="s1", name="S", is_active=True)]
    coord.homes = [{"id": "H1", "name": "Дом"}]
    coord.at_home = {"H1": True}
    coord._scenarios_poll = ThrottledPoll(300, "Scenario")
    coord._scenarios_poll.last_poll_at = time.time()
    coord._scenarios_poll.disabled = poll_disabled
    coord._scenario_api = MagicMock(return_value=api)
    coord._async_apply_push_data = MagicMock()
    for name in (
        "_ensure_homes",
        "_refresh_scenarios",
        "_throttled_poll",
        "_maybe_poll_scenarios",
        "async_refresh_scenarios",
        "async_execute_scenario",
        "async_set_scenario_active",
        "async_set_at_home",
    ):
        setattr(coord, name, getattr(SberHomeCoordinator, name).__get__(coord))
    coord.async_request_refresh = AsyncMock(side_effect=coord._maybe_poll_scenarios)
    return coord, api


@pytest.mark.parametrize("poll_disabled", [False, True], ids=["poll_throttled", "poll_disabled"])
async def test_denied_scenario_action_makes_deleted_scenario_unavailable(
    hass: HomeAssistant, poll_disabled: bool
) -> None:
    """Удалённый сценарий пропадает сразу после отказа, а не через 5 минут (или никогда).

    Раньше после 401 запрашивался только внеочередной опрос координатора, а он
    перечитывает сценарии не чаще раза в 5 минут и не перечитывает вовсе, если
    их опрос отключён после сбоя. Кнопка и тумблер удалённого сценария
    оставались доступны, и каждое нажатие давало ту же ошибку.
    """
    from custom_components.sberhome.button import SberScenarioButton
    from custom_components.sberhome.switch import SberAtHomeSwitch, SberScenarioActiveSwitch

    entry = _entry(hass)
    coord, api = _scenario_coordinator(hass, entry, poll_disabled=poll_disabled)
    button = SberScenarioButton(coord, "s1", "S")
    active = SberScenarioActiveSwitch(coord, "s1", "S")
    at_home = SberAtHomeSwitch(coord, "H1", "Дом")
    assert button.available and active.available and at_home.available

    with pytest.raises(HomeAssistantError) as exc_info:
        await button.async_press()
    assert exc_info.value.translation_key == "access_denied"
    await hass.async_block_till_done()

    api.list.assert_awaited_once()
    assert not button.available
    assert not active.available
    assert not at_home.available
    assert list(entry.async_get_active_flows(hass, {SOURCE_REAUTH})) == []


async def test_denied_at_home_action_rechecks_scenarios(hass: HomeAssistant) -> None:
    from custom_components.sberhome.switch import SberAtHomeSwitch

    entry = _entry(hass)
    coord, api = _scenario_coordinator(hass, entry, poll_disabled=False)
    at_home = SberAtHomeSwitch(coord, "H1", "Дом")

    with pytest.raises(HomeAssistantError):
        await at_home.async_turn_off()
    await hass.async_block_till_done()

    api.get_at_home.assert_awaited_once_with("H1")
    assert not at_home.available


async def test_failed_scenario_recheck_is_not_raised(hass: HomeAssistant) -> None:
    """Сбой фоновой перечитки сценариев не всплывает как ошибка задачи."""
    from custom_components.sberhome.button import SberScenarioButton

    entry = _entry(hass)
    coord, api = _scenario_coordinator(hass, entry, poll_disabled=False)
    api.list.side_effect = NetworkError("boom")
    button = SberScenarioButton(coord, "s1", "S")

    with pytest.raises(HomeAssistantError) as exc_info:
        await button.async_press()
    await hass.async_block_till_done()

    assert exc_info.value.translation_key == "access_denied"
    coord.async_request_refresh.assert_awaited_once()
    api.list.assert_awaited_once()
    assert button.available


async def test_entity_denied_request_does_not_start_reauth(hass: HomeAssistant) -> None:
    entry = _entry(hass)
    entity = _entity(hass, entry, RequestUnauthorized("Unauthorized after refresh: PUT /x"))
    entity.coordinator.async_request_refresh = AsyncMock()
    entity.coordinator.async_refresh_scenarios = AsyncMock()

    with pytest.raises(HomeAssistantError) as exc_info:
        await entity._async_send_attrs(_attrs())
    await hass.async_block_till_done()

    assert exc_info.value.translation_key == "access_denied"
    assert list(entry.async_get_active_flows(hass, {SOURCE_REAUTH})) == []
    entity.coordinator.async_request_refresh.assert_awaited_once()
    # Команда устройству: сценарии перечитывать незачем, хватает опроса устройств.
    entity.coordinator.async_refresh_scenarios.assert_not_awaited()


def test_exception_translations_exist_in_every_language() -> None:
    import json

    base = Path(__file__).resolve().parents[1] / "custom_components" / "sberhome"
    keys = {
        "access_denied",
        "auth_failed",
        "rate_limited",
        "command_rejected",
        "api_error",
        "cloud_unreachable",
        "cloud_error",
    }
    for path in [base / "strings.json", *sorted((base / "translations").glob("*.json"))]:
        exceptions = json.loads(path.read_text(encoding="utf-8")).get("exceptions", {})
        assert keys <= set(exceptions), path.name
        for key in keys:
            assert exceptions[key]["message"], (path.name, key)
        for key in ("command_rejected", "api_error"):
            assert "{status}" in exceptions[key]["message"], (path.name, key)
