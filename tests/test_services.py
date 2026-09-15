"""Сервисы SberHome в настоящем Home Assistant: регистрация и ошибки.

До исправления:

- сервисы регистрировались при настройке записи, поэтому до её загрузки (или
  после неудачной настройки) вызов ``sberhome.refresh`` в автоматизации
  падал с «сервис не найден», а редактор автоматизаций не знал их схему;
- при ошибке сервисы не поднимали исключение, а возвращали
  ``{"ok": false, "error": "..."}`` с английским или русским текстом без
  перевода: автоматизация считала вызов успешным.

Теперь сервисы живут с ``async_setup``, адресуются к записи через
необязательный ``config_entry_id`` и при ошибке поднимают
``ServiceValidationError`` / ``HomeAssistantError`` с ключом перевода.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome.action_errors import async_error_message
from custom_components.sberhome.aiosber.exceptions import (
    ApiError,
    NetworkError,
    RateLimitError,
    SberError,
)
from custom_components.sberhome.const import DOMAIN, NO_SPEAKERS_IN_HOME
from custom_components.sberhome.intents.reconciler import ReconcileReport

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "sberhome"

_VALID_STATE = [{"key": "on_off", "type": "BOOL", "bool_value": True}]

SERVICE_DATA: dict[str, dict[str, Any]] = {
    "refresh": {},
    "send_raw_command": {"device_id": "abc123", "state": _VALID_STATE},
    "reload_intents": {},
    "tts_send": {"message": "hi"},
    "ttc_send": {"message": "hi"},
}
"""Все сервисы уровня интеграции и минимальные корректные данные вызова."""


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations: None, monkeypatch: pytest.MonkeyPatch) -> None:
    """Дать загрузчику HA найти ``custom_components/sberhome`` (и при editable-установке)."""
    import custom_components

    real_dirs = [p for p in dict.fromkeys(custom_components.__path__) if Path(p).is_dir()]
    monkeypatch.setattr(custom_components, "__path__", real_dirs)


async def _setup(hass: HomeAssistant) -> None:
    """Настроить интеграцию без записей; HTTP-сервер HA сервисам не нужен."""
    hass.config.components.add("http")
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


def _home(home_id: str) -> MagicMock:
    home = MagicMock(id=home_id)
    home.name = f"Дом {home_id}"
    return home


def _coordinator() -> MagicMock:
    coord = MagicMock()
    coord.client.transport.put = AsyncMock()
    coord.async_refresh = AsyncMock()
    coord.last_update_success = True
    coord.async_refresh_staros = AsyncMock(return_value=True)
    coord.state_cache.get_homes.return_value = [_home("H1"), _home("H2")]
    mapping = {"dA": "H1", "dB": "H2"}
    coord.state_cache.device_home_id.side_effect = mapping.get
    coord.tts_service.send = AsyncMock()
    coord.ttc_service.send = AsyncMock()
    coord.async_shutdown = AsyncMock()
    return coord


def _entry(
    hass: HomeAssistant, *, loaded: bool, title: str = "SberHome"
) -> tuple[MockConfigEntry, MagicMock]:
    entry = MockConfigEntry(domain=DOMAIN, title=title, data={})
    entry.add_to_hass(hass)
    coord = _coordinator()
    if loaded:
        entry.mock_state(hass, ConfigEntryState.LOADED)
        entry.runtime_data = coord
    return entry, coord


async def _call(hass: HomeAssistant, service: str, data: dict[str, Any] | None = None) -> Any:
    payload = SERVICE_DATA[service] if data is None else data
    return await hass.services.async_call(
        DOMAIN, service, payload, blocking=True, return_response=True
    )


# --- action-setup ---------------------------------------------------------------


async def test_services_exist_before_any_entry(hass: HomeAssistant) -> None:
    await _setup(hass)

    for service in SERVICE_DATA:
        assert hass.services.has_service(DOMAIN, service), service


@pytest.mark.parametrize("service", list(SERVICE_DATA))
async def test_call_without_entries_raises_translated(hass: HomeAssistant, service: str) -> None:
    await _setup(hass)

    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, service)

    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == "no_config_entry"


@pytest.mark.parametrize("service", list(SERVICE_DATA))
@pytest.mark.parametrize("explicit", [False, True], ids=["default_entry", "config_entry_id"])
async def test_call_with_not_loaded_entry_raises_translated(
    hass: HomeAssistant, service: str, explicit: bool
) -> None:
    await _setup(hass)
    entry, coord = _entry(hass, loaded=False, title="Квартира")
    data = dict(SERVICE_DATA[service])
    if explicit:
        data["config_entry_id"] = entry.entry_id

    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, service, data)

    assert exc_info.value.translation_key == "config_entry_not_loaded"
    assert exc_info.value.translation_placeholders == {"title": "Квартира"}
    coord.client.transport.put.assert_not_awaited()


async def test_call_after_entry_unloaded_raises_translated(hass: HomeAssistant) -> None:
    await _setup(hass)
    entry, coord = _entry(hass, loaded=True)
    await _call(hass, "refresh")
    entry.mock_state(hass, ConfigEntryState.NOT_LOADED)

    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, "refresh")

    assert exc_info.value.translation_key == "config_entry_not_loaded"
    coord.async_refresh.assert_awaited_once()


@pytest.mark.parametrize("service", list(SERVICE_DATA))
async def test_unknown_config_entry_id_raises_translated(hass: HomeAssistant, service: str) -> None:
    await _setup(hass)
    _entry(hass, loaded=True)
    foreign = MockConfigEntry(domain="other_domain")
    foreign.add_to_hass(hass)

    for entry_id in ("missing", foreign.entry_id):
        with pytest.raises(ServiceValidationError) as exc_info:
            await _call(hass, service, {**SERVICE_DATA[service], "config_entry_id": entry_id})
        assert exc_info.value.translation_key == "config_entry_not_found"
        assert exc_info.value.translation_placeholders == {"config_entry_id": entry_id}


async def test_config_entry_id_selects_the_entry(hass: HomeAssistant) -> None:
    await _setup(hass)
    _first, first_coord = _entry(hass, loaded=True, title="Первая")
    second, second_coord = _entry(hass, loaded=True, title="Вторая")

    result = await _call(hass, "refresh", {"config_entry_id": second.entry_id})

    assert result == {"ok": True, "refreshed_entries": 1}
    second_coord.async_refresh.assert_awaited_once()
    second_coord.async_refresh_staros.assert_awaited_once()
    first_coord.async_refresh.assert_not_awaited()


async def test_default_entry_is_the_panel_entry(hass: HomeAssistant) -> None:
    """Без config_entry_id — первая загруженная запись, как у панели."""
    await _setup(hass)
    _entry(hass, loaded=False, title="Сломанная")
    _loaded, coord = _entry(hass, loaded=True, title="Рабочая")

    await _call(hass, "refresh")

    coord.async_refresh.assert_awaited_once()


@pytest.mark.parametrize("service", ["send_raw_command", "reload_intents"])
async def test_admin_services_still_reject_non_admin(hass: HomeAssistant, service: str) -> None:
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)
    await hass.auth.async_create_user("owner", group_ids=["system-admin"])
    user = await hass.auth.async_create_user("tester", group_ids=["system-users"])

    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            service,
            SERVICE_DATA[service],
            blocking=True,
            context=Context(user_id=user.id),
            return_response=True,
        )
    coord.client.transport.put.assert_not_awaited()


# --- action-exceptions: refresh ------------------------------------------------


class _FailingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Настоящий координатор HA, чей опрос падает заданной ошибкой.

    ``DataUpdateCoordinator`` сам ловит ошибки опроса и только выставляет
    ``last_update_success = False`` — на этом сервис и молчал.
    """

    def __init__(
        self, hass: HomeAssistant, entry: MockConfigEntry, error: Exception | None
    ) -> None:
        super().__init__(
            hass, logging.getLogger(__name__), config_entry=entry, name="sberhome test"
        )
        self.error = error
        self.rate_limited = False
        self.staros_available = True
        self.async_refresh_staros = AsyncMock(return_value=True)
        self.reset_background_polls = MagicMock()

    def has_staros_settings(self) -> bool:
        return self.staros_available

    async def _async_update_data(self) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return {}


def _failing_entry(hass: HomeAssistant, error: Exception | None) -> _FailingCoordinator:
    entry = MockConfigEntry(domain=DOMAIN, title="SberHome", data={})
    entry.add_to_hass(hass)
    entry.mock_state(hass, ConfigEntryState.LOADED)
    coord = _FailingCoordinator(hass, entry, error)
    entry.runtime_data = coord
    return coord


def _update_failed(cause: Exception) -> UpdateFailed:
    try:
        raise UpdateFailed("Error communicating with API") from cause
    except UpdateFailed as err:
        return err


@pytest.mark.parametrize(
    ("error", "key", "placeholders"),
    [
        (_update_failed(NetworkError("dns")), "cloud_unreachable", None),
        (_update_failed(ApiError(503, "down")), "api_error", {"status": "503"}),
        (_update_failed(RateLimitError(retry_after=30)), "rate_limited", None),
        (_update_failed(SberError("odd")), "cloud_error", None),
        (ConfigEntryAuthFailed("expired"), "auth_failed", None),
        (RuntimeError("bug"), "refresh_failed", None),
    ],
    ids=["network", "api", "rate_limit", "sber", "auth", "unexpected"],
)
async def test_refresh_failure_raises_translated(
    hass: HomeAssistant, error: Exception, key: str, placeholders: dict[str, str] | None
) -> None:
    """Сбой опроса облака останавливает автоматизацию, а не отвечает ``ok: true``."""
    await _setup(hass)
    coord = _failing_entry(hass, error)

    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, "refresh")

    assert type(exc_info.value) is HomeAssistantError
    assert exc_info.value.translation_domain == DOMAIN
    assert exc_info.value.translation_key == key
    assert exc_info.value.translation_placeholders == placeholders
    assert exc_info.value.__cause__ is coord.last_exception
    coord.async_refresh_staros.assert_not_awaited()


async def test_refresh_during_rate_limit_pause_raises_rate_limited(hass: HomeAssistant) -> None:
    """Пока облако просит подождать, опрос не уходит — и сервис говорит об этом."""
    await _setup(hass)
    coord = _failing_entry(hass, UpdateFailed("Rate limited by Sber cloud, next update in 40s"))
    coord.rate_limited = True

    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, "refresh")

    assert exc_info.value.translation_key == "rate_limited"


async def test_refresh_is_not_debounced(hass: HomeAssistant) -> None:
    """Два вызова подряд — два опроса: debounce не подменяет результат старым."""
    await _setup(hass)
    coord = _failing_entry(hass, None)
    await _call(hass, "refresh")
    coord.error = _update_failed(NetworkError("dns"))

    with pytest.raises(HomeAssistantError):
        await _call(hass, "refresh")


async def test_refresh_speaker_settings_failure_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    coord = _failing_entry(hass, None)
    coord.async_refresh_staros.return_value = False

    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, "refresh")

    assert exc_info.value.translation_key == "speaker_settings_refresh_failed"


async def test_refresh_without_speaker_settings_domain_succeeds(hass: HomeAssistant) -> None:
    """SMS-вход или отказ облака в доступе к настройкам колонок — не сбой обновления."""
    await _setup(hass)
    coord = _failing_entry(hass, None)
    coord.async_refresh_staros.return_value = False
    coord.staros_available = False

    result = await _call(hass, "refresh")

    assert result == {"ok": True, "refreshed_entries": 1}
    coord.reset_background_polls.assert_called_once()
    assert coord.last_update_success


# --- action-exceptions: send_raw_command ---------------------------------------


@pytest.mark.parametrize(
    ("error", "exc_type", "key"),
    [
        (NetworkError("boom"), HomeAssistantError, "cloud_unreachable"),
        (ApiError(500, "boom"), HomeAssistantError, "api_error"),
        (ApiError(400, "boom"), ServiceValidationError, "command_rejected"),
    ],
)
async def test_send_raw_command_cloud_error_raises_translated(
    hass: HomeAssistant, error: Exception, exc_type: type[HomeAssistantError], key: str
) -> None:
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)
    coord.client.transport.put.side_effect = error

    with pytest.raises(exc_type) as exc_info:
        await _call(hass, "send_raw_command")

    assert type(exc_info.value) is exc_type
    assert exc_info.value.translation_key == key


async def test_send_raw_command_returns_payload_on_success(hass: HomeAssistant) -> None:
    await _setup(hass)
    _entry(hass, loaded=True)

    result = await _call(hass, "send_raw_command")

    assert result == {"ok": True, "device_id": "abc123", "state": _VALID_STATE}


# --- action-exceptions: reload_intents -----------------------------------------


def _patch_yaml(**kwargs: Any) -> Any:
    return patch("homeassistant.config.load_yaml_config_file", **kwargs)


async def test_reload_intents_unreadable_yaml_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    _entry(hass, loaded=True)

    with (
        _patch_yaml(side_effect=FileNotFoundError("configuration.yaml")),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await _call(hass, "reload_intents")

    assert type(exc_info.value) is HomeAssistantError
    assert exc_info.value.translation_key == "yaml_unavailable"


@pytest.mark.parametrize(
    "load",
    [
        pytest.param({"side_effect": HomeAssistantError("bad indent")}, id="parse"),
        pytest.param({"return_value": {DOMAIN: {"intents": "not-a-list"}}}, id="schema"),
        pytest.param(
            {
                "return_value": {
                    DOMAIN: {
                        "listeners": [
                            {"slug": "dup", "name": "A", "filter": {"trigger_type": "TIME"}},
                            {"slug": "dup", "name": "B", "filter": {"trigger_type": "TIME"}},
                        ]
                    }
                }
            },
            id="duplicate-listener-slug",
        ),
    ],
)
async def test_reload_intents_invalid_yaml_raises_validation_error(
    hass: HomeAssistant, load: dict[str, Any]
) -> None:
    await _setup(hass)
    _entry(hass, loaded=True)

    with _patch_yaml(**load), pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, "reload_intents")

    assert exc_info.value.translation_key == "yaml_invalid"
    assert exc_info.value.translation_placeholders["error"]


async def test_reload_intents_reconcile_failure_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)
    report = ReconcileReport(created=["ok_one"], failed=[("kitchen", "HTTP 500")])

    with (
        _patch_yaml(return_value={}),
        patch("custom_components.sberhome.reconcile_intents", AsyncMock(return_value=report)),
        pytest.raises(HomeAssistantError) as exc_info,
    ):
        await _call(hass, "reload_intents")

    assert exc_info.value.translation_key == "intents_reconcile_failed"
    assert exc_info.value.translation_placeholders == {"count": "1", "intents": "kitchen"}
    # Listeners применены, даже если часть intent'ов не прошла.
    coord.listener_registry.replace.assert_called_once_with([])


async def test_reload_intents_returns_report_on_success(hass: HomeAssistant) -> None:
    await _setup(hass)
    entry, _coord = _entry(hass, loaded=True)
    report = ReconcileReport(unchanged=["kitchen"])

    with (
        _patch_yaml(return_value={}),
        patch("custom_components.sberhome.reconcile_intents", AsyncMock(return_value=report)),
    ):
        result = await _call(hass, "reload_intents")

    assert result["ok"] is True
    assert result["intents_count"] == 0
    assert result["results"] == {entry.entry_id: report.to_dict()}


# --- action-exceptions: tts_send / ttc_send ------------------------------------


def _no_speakers(home: str) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key=NO_SPEAKERS_IN_HOME,
        translation_placeholders={"home": home},
    )


@pytest.mark.parametrize(
    ("service", "attr"), [("tts_send", "tts_service"), ("ttc_send", "ttc_service")]
)
async def test_surrogate_failure_in_one_home_raises_after_all_homes(
    hass: HomeAssistant, service: str, attr: str
) -> None:
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)
    send = getattr(coord, attr).send
    send.side_effect = [NetworkError("boom"), None]

    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, service, {"message": "hi", "device_ids": ["dA", "dB"]})

    assert exc_info.value.translation_key == "cloud_unreachable"
    assert [c.args[0] for c in send.await_args_list] == ["H1", "H2"]


async def test_broadcast_skips_homes_without_speakers(hass: HomeAssistant) -> None:
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)
    coord.tts_service.send.side_effect = [_no_speakers("Дача"), None]

    result = await _call(hass, "tts_send", {"message": "hi"})

    assert result == {"ok": True, "results": {"H2": "ok"}}


async def test_broadcast_without_any_speaker_raises(hass: HomeAssistant) -> None:
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)
    coord.tts_service.send.side_effect = [_no_speakers("H1"), _no_speakers("H2")]

    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, "tts_send", {"message": "hi"})

    assert exc_info.value.translation_key == "speakers_not_found"


async def test_explicit_speaker_in_home_without_speakers_raises(hass: HomeAssistant) -> None:
    """Колонка указана явно — отсутствие колонок в доме не замалчивается."""
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)
    coord.ttc_service.send.side_effect = _no_speakers("Дом H1")

    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, "ttc_send", {"message": "hi", "device_ids": ["dA"]})

    assert exc_info.value.translation_key == NO_SPEAKERS_IN_HOME


async def test_unknown_device_ids_raise_validation_error(hass: HomeAssistant) -> None:
    await _setup(hass)
    _entry_obj, coord = _entry(hass, loaded=True)

    with pytest.raises(ServiceValidationError) as exc_info:
        await _call(hass, "tts_send", {"message": "hi", "device_ids": ["zzz"]})

    assert exc_info.value.translation_key == "speakers_not_found"
    coord.tts_service.send.assert_not_awaited()


# --- exception-translations -----------------------------------------------------


NEW_EXCEPTION_KEYS = {
    "config_entry_not_found": {"config_entry_id"},
    "no_config_entry": set(),
    "config_entry_not_loaded": {"title"},
    "yaml_unavailable": {"error"},
    "yaml_invalid": {"error"},
    "intents_reconcile_failed": {"count", "intents"},
    "speakers_not_found": set(),
    "no_speakers_in_home": {"home"},
    "message_template_error": {"error"},
}
"""Ключи ошибок сервисов и плейсхолдеры, которые им передаются."""


def _translation_files() -> list[Path]:
    return [BASE / "strings.json", *sorted((BASE / "translations").glob("*.json"))]


@pytest.mark.parametrize("path", _translation_files(), ids=lambda p: p.name)
def test_service_exceptions_are_translated(path: Path) -> None:
    import string

    exceptions = json.loads(path.read_text(encoding="utf-8"))["exceptions"]
    for key, placeholders in NEW_EXCEPTION_KEYS.items():
        message = exceptions[key]["message"]
        used = {name for _, name, _, _ in string.Formatter().parse(message) if name}
        assert used == placeholders, (path.name, key)


@pytest.mark.parametrize("path", _translation_files(), ids=lambda p: p.name)
def test_every_service_and_field_is_translated(path: Path) -> None:
    services_yaml = yaml.safe_load((BASE / "services.yaml").read_text(encoding="utf-8"))
    services = json.loads(path.read_text(encoding="utf-8"))["services"]
    for service, schema in services_yaml.items():
        assert services[service]["name"], (path.name, service)
        assert services[service]["description"], (path.name, service)
        for field in schema.get("fields", {}):
            assert services[service]["fields"][field]["name"], (path.name, service, field)
            assert services[service]["fields"][field]["description"], (path.name, service, field)


@pytest.mark.parametrize("path", _translation_files(), ids=lambda p: p.name)
def test_translation_placeholders_are_identifiers(path: Path) -> None:
    """Фигурные скобки в переводах — только плейсхолдеры с именем-идентификатором.

    Так проверяет hassfest (``validate_placeholders``): JSON-пример вида
    ``[{"key": ...}]`` в описании поля он принимает за плейсхолдер ``"key"`` и
    отклоняет весь файл переводов.
    """
    import string

    def _strings(node: Any, where: str) -> list[tuple[str, str]]:
        if isinstance(node, dict):
            return [s for key, value in node.items() for s in _strings(value, f"{where}.{key}")]
        return [(where, node)] if isinstance(node, str) else []

    for where, value in _strings(json.loads(path.read_text(encoding="utf-8")), path.name):
        names = [name for _, name, _, _ in string.Formatter().parse(value) if name]
        assert all(name.isidentifier() for name in names), (where, names)


async def test_panel_error_message_uses_ha_language(hass: HomeAssistant) -> None:
    """WS-команды панели отдают ошибку текстом на языке Home Assistant, а не ключом."""
    hass.config.language = "ru"
    err = _no_speakers("Дача")

    message = await async_error_message(hass, err)

    assert "Дача" in message
    assert "нет колонок Sber" in message
    assert await async_error_message(hass, RuntimeError("boom")) == "boom"


async def test_panel_tts_test_endpoint_shows_translated_error(hass: HomeAssistant) -> None:
    from custom_components.sberhome.websocket_api.tts_surrogate import ws_test_tts_surrogate

    hass.config.language = "ru"
    _entry_obj, coord = _entry(hass, loaded=True)
    coord.tts_service.send.side_effect = _no_speakers("Дача")
    connection = MagicMock()

    await ws_test_tts_surrogate.__wrapped__(
        hass,
        connection,
        {"id": 1, "type": "sberhome/tts_surrogate/test", "home_id": "H1", "message": "x"},
    )

    result = connection.send_result.call_args.args[1]
    assert result["ok"] is False
    assert "В доме «Дача» нет колонок Sber" in result["error"]
