"""Одна запись SberHome на Home Assistant.

Панель и её WebSocket-команды всегда работают с первой загруженной записью,
поэтому вторая запись (второй аккаунт Сбера) оставалась неуправляемой. Манифест
объявляет ``single_config_entry``: Home Assistant не даёт начать новую
настройку, пока запись уже есть, но reauth пропускает. Записи, созданные до
этого, Home Assistant не трогает — о них сообщает замечание в Repairs.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_USER,
    ConfigEntry,
    ConfigEntryDisabler,
    ConfigEntryState,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.sberhome.aiosber.const import AUTH_METHOD_SBERID
from custom_components.sberhome.const import CONF_AUTH_METHOD, CONF_TOKEN, DOMAIN
from custom_components.sberhome.single_entry import (
    ISSUE_ID,
    async_setup_multiple_entries_issue,
    async_update_multiple_entries_issue,
)
from custom_components.sberhome.websocket_api._common import get_config_entry

from .test_config_flow import _make_token_with_sub

BASE = Path(__file__).resolve().parents[1] / "custom_components" / "sberhome"


@pytest.fixture(autouse=True)
def _custom_integrations(enable_custom_integrations: None) -> None:
    """Дать загрузчику HA найти ``custom_components/sberhome``."""


@pytest.fixture(autouse=True)
def mock_entry_setup() -> Iterator[tuple[AsyncMock, AsyncMock]]:
    """Настройка/выгрузка записи без облака Сбера и без платформ.

    Autouse: при завершении теста hass выгружает записи, помеченные LOADED.
    """
    with (
        patch("custom_components.sberhome.async_setup_entry", AsyncMock(return_value=True)) as s,
        patch("custom_components.sberhome.async_unload_entry", AsyncMock(return_value=True)) as u,
    ):
        yield s, u


def _entry(
    hass: HomeAssistant,
    entry_id: str,
    *,
    title: str = "SberHome",
    state: ConfigEntryState = ConfigEntryState.NOT_LOADED,
    **kwargs,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        entry_id=entry_id,
        title=title,
        unique_id=kwargs.pop("unique_id", f"sub-{entry_id}"),
        data=kwargs.pop(
            "data",
            {CONF_AUTH_METHOD: AUTH_METHOD_SBERID, CONF_TOKEN: _make_token_with_sub("x")},
        ),
        state=state,
        **kwargs,
    )
    entry.add_to_hass(hass)
    return entry


def test_manifest_declares_single_config_entry() -> None:
    manifest = json.loads((BASE / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["single_config_entry"] is True


# --- новые настройки ---------------------------------------------------------


async def test_first_user_flow_is_allowed(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"


async def test_second_user_flow_aborts(hass: HomeAssistant) -> None:
    """Второй аккаунт добавить нельзя — панель им всё равно не управляла бы."""
    _entry(hass, "e1")

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
    assert hass.config_entries.flow.async_progress_by_handler(DOMAIN) == []


async def test_ignored_entry_does_not_block_user_flow(hass: HomeAssistant) -> None:
    _entry(hass, "ignored", source=SOURCE_IGNORE)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})

    assert result["type"] is FlowResultType.MENU


# --- reauth ------------------------------------------------------------------


@pytest.mark.parametrize("extra_entries", [0, 1])
async def test_reauth_still_works(hass: HomeAssistant, extra_entries: int) -> None:
    """Reauth проходит и при одной записи, и у тех, у кого их уже несколько."""
    sub = "account-sub"
    for index in range(extra_entries):
        _entry(hass, f"extra{index}")
    entry = _entry(
        hass,
        "target",
        unique_id=sub,
        data={CONF_AUTH_METHOD: AUTH_METHOD_SBERID, CONF_TOKEN: {"access_token": "old"}},
    )
    new_token = _make_token_with_sub(sub)
    client = MagicMock()
    client.token = new_token
    client.create_authorization_url.return_value = "https://id.sber.ru/authorize"
    client.aclose = AsyncMock()

    with (
        patch("custom_components.sberhome.config_flow.async_init_ssl", AsyncMock()),
        patch("custom_components.sberhome.config_flow.httpx.AsyncClient"),
        patch("custom_components.sberhome.config_flow.SberAPI", return_value=client),
        patch(
            "custom_components.sberhome.config_flow.get_url",
            return_value="http://ha.local:8123",
        ),
        patch("custom_components.sberhome.config_flow.ConfigFlow._register_views"),
        patch.object(hass.config_entries, "async_schedule_reload") as reload,
    ):
        result = await entry.start_reauth_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] is FlowResultType.EXTERNAL_STEP

        # Колбэк страницы авторизации продвигает внешний шаг.
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] is FlowResultType.EXTERNAL_STEP_DONE

        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == new_token
    reload.assert_called_once_with(entry.entry_id)
    assert len(hass.config_entries.async_entries(DOMAIN)) == extra_entries + 1


# --- уже существующие несколько записей ----------------------------------------


def _issue(hass: HomeAssistant) -> ir.IssueEntry | None:
    return ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)


def _warnings(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [
        r
        for r in caplog.records
        if r.levelno == logging.WARNING and r.name.startswith("custom_components.sberhome")
    ]


def _assert_issue_names_panel_entry(hass: HomeAssistant) -> None:
    """Замечание называет ту же запись, с которой работает панель."""
    panel_entry = get_config_entry(hass)
    assert panel_entry is not None
    assert _issue(hass).translation_placeholders["active"] == panel_entry.title


async def test_single_entry_has_no_issue(hass: HomeAssistant) -> None:
    _entry(hass, "e1", state=ConfigEntryState.LOADED)

    async_update_multiple_entries_issue(hass)

    assert _issue(hass) is None


async def test_multiple_entries_raise_issue_naming_panel_entry(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Активная — та, что берёт панель: первая загруженная, а не первая в списке."""
    _entry(hass, "e1", title="SberHome", state=ConfigEntryState.SETUP_ERROR)
    _entry(hass, "e2", title="SberHome (SMS · 78001234567)", state=ConfigEntryState.LOADED)
    _entry(hass, "e3", title="Дача", state=ConfigEntryState.LOADED)

    with caplog.at_level(logging.WARNING, logger="custom_components.sberhome"):
        async_update_multiple_entries_issue(hass)

    issue = _issue(hass)
    assert issue is not None
    assert issue.severity is ir.IssueSeverity.WARNING
    assert not issue.is_fixable
    assert issue.translation_key == ISSUE_ID
    assert issue.translation_placeholders == {
        "count": "3",
        "active": "SberHome (SMS · 78001234567)",
        "others": "«SberHome», «Дача»",
    }
    _assert_issue_names_panel_entry(hass)
    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "entry_id=e2" in warnings[0].getMessage()


async def test_first_entry_is_active_when_nothing_loaded(hass: HomeAssistant) -> None:
    _entry(hass, "e1", title="Первый", state=ConfigEntryState.SETUP_ERROR)
    _entry(hass, "e2", title="Второй", state=ConfigEntryState.SETUP_RETRY)

    async_update_multiple_entries_issue(hass)

    assert _issue(hass).translation_placeholders["active"] == "Первый"


async def test_disabled_and_ignored_entries_do_not_count(hass: HomeAssistant) -> None:
    _entry(hass, "e1", state=ConfigEntryState.LOADED)
    extra = _entry(hass, "e2", state=ConfigEntryState.LOADED)
    async_update_multiple_entries_issue(hass)
    assert _issue(hass) is not None

    # Отключение: к моменту unload запись ещё LOADED, но уже disabled_by.
    extra.disabled_by = ConfigEntryDisabler.USER
    _entry(hass, "ignored", source=SOURCE_IGNORE)
    async_update_multiple_entries_issue(hass)

    assert _issue(hass) is None


# --- пересчёт по изменениям записей (без реального setup) ---------------------


async def test_warning_is_logged_once_during_startup(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Каждая смена состояния пересчитывает замечание — журнал не спамим."""
    async_setup_multiple_entries_issue(hass)
    first = _entry(hass, "e1", title="Первый")
    second = _entry(hass, "e2", title="Второй")

    with caplog.at_level(logging.WARNING, logger="custom_components.sberhome"):
        for entry in (first, second):
            entry.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
        first.mock_state(hass, ConfigEntryState.LOADED)
        second.mock_state(hass, ConfigEntryState.LOADED)

    assert len(_warnings(caplog)) == 1
    _assert_issue_names_panel_entry(hass)


async def test_second_entry_finishing_setup_first(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Вторая запись загрузилась раньше — панель всё равно окажется на первой."""
    async_setup_multiple_entries_issue(hass)
    first = _entry(hass, "e1", title="Первый")
    second = _entry(hass, "e2", title="Второй")

    with caplog.at_level(logging.WARNING, logger="custom_components.sberhome"):
        first.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
        second.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
        second.mock_state(hass, ConfigEntryState.LOADED)
        assert _issue(hass).translation_placeholders["active"] == "Первый"
        first.mock_state(hass, ConfigEntryState.LOADED)

    _assert_issue_names_panel_entry(hass)
    assert _issue(hass).translation_placeholders["active"] == "Первый"
    assert len(_warnings(caplog)) == 1


async def test_failed_first_entry_hands_issue_to_loaded_one(hass: HomeAssistant) -> None:
    """Первая запись не настроилась — замечание переходит к той, что берёт панель."""
    async_setup_multiple_entries_issue(hass)
    first = _entry(hass, "e1", title="Первый")
    second = _entry(hass, "e2", title="Второй")

    first.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    second.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
    second.mock_state(hass, ConfigEntryState.LOADED)
    first.mock_state(hass, ConfigEntryState.SETUP_RETRY)

    _assert_issue_names_panel_entry(hass)
    assert _issue(hass).translation_placeholders["active"] == "Второй"


async def test_setup_retry_attempts_do_not_flip_issue(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    """Повторные попытки настройки не переключают замечание туда-обратно."""
    async_setup_multiple_entries_issue(hass)
    first = _entry(hass, "e1", title="Первый", state=ConfigEntryState.SETUP_RETRY)
    second = _entry(hass, "e2", title="Второй", state=ConfigEntryState.LOADED)
    async_update_multiple_entries_issue(hass)
    caplog.clear()

    with caplog.at_level(logging.WARNING, logger="custom_components.sberhome"):
        for _ in range(3):
            first.mock_state(hass, ConfigEntryState.SETUP_IN_PROGRESS)
            first.mock_state(hass, ConfigEntryState.SETUP_RETRY)

    assert _warnings(caplog) == []
    assert _issue(hass).translation_placeholders["active"] == second.title


async def test_issue_ignores_other_domains(hass: HomeAssistant) -> None:
    async_setup_multiple_entries_issue(hass)
    _entry(hass, "e1", state=ConfigEntryState.LOADED)
    _entry(hass, "e2", state=ConfigEntryState.LOADED)
    other = MockConfigEntry(domain="other_domain", entry_id="o1")
    other.add_to_hass(hass)

    with patch(
        "custom_components.sberhome.single_entry.async_update_multiple_entries_issue"
    ) as update:
        other.mock_state(hass, ConfigEntryState.LOADED)

    update.assert_not_called()


# --- реальные операции Home Assistant ------------------------------------------


async def _setup_integration(hass: HomeAssistant) -> None:
    with patch("custom_components.sberhome.async_setup", AsyncMock(return_value=True)):
        # async_setup подменён, поэтому подписку оформляем как в настоящем.
        async_setup_multiple_entries_issue(hass)
        assert await hass.config_entries.async_setup(
            hass.config_entries.async_entries(DOMAIN)[0].entry_id
        )
    await hass.async_block_till_done()


async def test_async_setup_subscribes_to_entry_changes(hass: HomeAssistant) -> None:
    """async_setup интеграции оформляет подписку до настройки записей."""
    from custom_components.sberhome import async_setup

    with patch("custom_components.sberhome.async_setup_multiple_entries_issue") as subscribe:
        assert await async_setup(hass, {}) is True

    subscribe.assert_called_once_with(hass)


async def test_reloading_panel_entry_keeps_issue_on_it(
    hass: HomeAssistant,
    caplog: pytest.LogCaptureFixture,
    mock_entry_setup: tuple[AsyncMock, AsyncMock],
) -> None:
    """Reload первой записи (настройки, reauth) не переносит замечание на вторую."""
    first = _entry(hass, "e1", title="Первый")
    _entry(hass, "e2", title="Второй")
    await _setup_integration(hass)
    for entry in hass.config_entries.async_entries(DOMAIN):
        assert entry.state is ConfigEntryState.LOADED
    _assert_issue_names_panel_entry(hass)

    seen: list[str] = []

    async def _unload(hass_: HomeAssistant, entry: ConfigEntry) -> bool:
        seen.append(_issue(hass_).translation_placeholders["active"])
        return True

    mock_entry_setup[1].side_effect = _unload
    with caplog.at_level(logging.WARNING, logger="custom_components.sberhome"):
        caplog.clear()
        assert await hass.config_entries.async_reload(first.entry_id)
        await hass.async_block_till_done()

    assert seen == ["Первый"]
    assert first.state is ConfigEntryState.LOADED
    _assert_issue_names_panel_entry(hass)
    assert _issue(hass).translation_placeholders["active"] == "Первый"
    assert _warnings(caplog) == []


async def test_disabling_panel_entry_moves_issue_to_remaining(
    hass: HomeAssistant, mock_entry_setup: tuple[AsyncMock, AsyncMock]
) -> None:
    first = _entry(hass, "e1", title="Первый")
    _entry(hass, "e2", title="Второй")
    _entry(hass, "e3", title="Третий")
    await _setup_integration(hass)
    assert _issue(hass).translation_placeholders["active"] == "Первый"

    await hass.config_entries.async_set_disabled_by(first.entry_id, ConfigEntryDisabler.USER)
    await hass.async_block_till_done()

    assert _issue(hass).translation_placeholders == {
        "count": "2",
        "active": "Второй",
        "others": "«Третий»",
    }
    _assert_issue_names_panel_entry(hass)


async def test_disabling_extra_entry_clears_issue(
    hass: HomeAssistant, mock_entry_setup: tuple[AsyncMock, AsyncMock]
) -> None:
    _entry(hass, "e1")
    extra = _entry(hass, "e2")
    await _setup_integration(hass)
    assert _issue(hass) is not None

    await hass.config_entries.async_set_disabled_by(extra.entry_id, ConfigEntryDisabler.USER)
    await hass.async_block_till_done()

    assert _issue(hass) is None


async def test_removing_extra_entry_clears_issue(
    hass: HomeAssistant, mock_entry_setup: tuple[AsyncMock, AsyncMock]
) -> None:
    """Удаление лишней записи через HA снимает замечание."""
    _entry(hass, "e1")
    extra = _entry(hass, "e2")
    await _setup_integration(hass)
    assert _issue(hass) is not None

    await hass.config_entries.async_remove(extra.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass) is None


async def test_removing_panel_entry_moves_issue(
    hass: HomeAssistant, mock_entry_setup: tuple[AsyncMock, AsyncMock]
) -> None:
    first = _entry(hass, "e1", title="Первый")
    _entry(hass, "e2", title="Второй")
    _entry(hass, "e3", title="Третий")
    await _setup_integration(hass)

    await hass.config_entries.async_remove(first.entry_id)
    await hass.async_block_till_done()

    assert _issue(hass).translation_placeholders["active"] == "Второй"
    _assert_issue_names_panel_entry(hass)


def test_issue_text_exists_in_every_language() -> None:
    files = [BASE / "strings.json", *sorted((BASE / "translations").glob("*.json"))]
    for path in files:
        issue = json.loads(path.read_text(encoding="utf-8"))["issues"][ISSUE_ID]
        assert issue["title"], path.name
        for placeholder in ("{count}", "{active}", "{others}"):
            assert placeholder in issue["description"], (path.name, placeholder)
