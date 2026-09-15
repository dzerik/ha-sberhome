"""Замечание о нескольких записях SberHome в одном Home Assistant.

Интеграция поддерживает один аккаунт Сбера: панель и её WebSocket-команды
работают с одной загруженной записью (``websocket_api._common.get_config_entry``).
Манифест объявляет ``single_config_entry``, и Home Assistant больше не даёт
добавить вторую запись. Но записи, созданные раньше, он не трогает:
все они по-прежнему загружаются, а управлять из панели можно только одной.
Молча оставлять пользователя с неуправляемой записью нельзя, поэтому здесь
создаётся замечание в Repairs и пишется предупреждение в журнал.

Замечание пересчитывается после каждого изменения записей SberHome
(``SIGNAL_CONFIG_ENTRY_CHANGED``): добавления, удаления, смены состояния.
Пересчёт внутри ``async_setup_entry``/``async_unload_entry`` не годится —
в этот момент запись ещё в переходном состоянии, и замечание называло бы
не ту запись, которую панель возьмёт, когда настройка или reload завершится.
"""

from __future__ import annotations

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
    ConfigEntryState,
)
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, LOGGER

ISSUE_ID = "multiple_config_entries"
"""Идентификатор замечания в Repairs (и ключ перевода в ``issues``)."""

_EXPECTED_LOADED_STATES = frozenset(
    {
        ConfigEntryState.LOADED,
        ConfigEntryState.SETUP_IN_PROGRESS,
        ConfigEntryState.UNLOAD_IN_PROGRESS,
        ConfigEntryState.NOT_LOADED,
    }
)
"""Состояния записи, которая загружена или будет загружена после перехода.

``NOT_LOADED`` и оба ``*_IN_PROGRESS`` — промежуточные шаги старта и reload:
после них запись снова станет ``LOADED`` и панель вернётся к ней. Отключённые
записи сюда не попадают — их отсекает фильтр ``include_disabled=False``,
удалённые — исчезают из реестра. Ошибочные состояния (``SETUP_RETRY``,
``SETUP_ERROR`` и т.п.) не считаются: панель такую запись не берёт.
"""

_TRANSITIONAL_STATES = frozenset(
    {ConfigEntryState.SETUP_IN_PROGRESS, ConfigEntryState.UNLOAD_IN_PROGRESS}
)
"""Переходы, на которые пересчёт не нужен: итог придёт следующим событием.

Иначе каждая попытка ``SETUP_RETRY`` на миг меняла бы активную запись и
дважды писала бы предупреждение в журнал.
"""


@callback
def async_setup_multiple_entries_issue(hass: HomeAssistant) -> CALLBACK_TYPE:
    """Подписаться на изменения записей SberHome и пересчитывать замечание.

    Вызывается один раз из ``async_setup`` — до настройки записей, чтобы
    ни одно изменение их состояния не прошло мимо.

    Args:
        hass: Home Assistant.

    Returns:
        Функция отписки.
    """

    @callback
    def _async_entry_changed(change: ConfigEntryChange, entry: ConfigEntry) -> None:
        if entry.domain != DOMAIN:
            return
        if change is ConfigEntryChange.UPDATED and entry.state in _TRANSITIONAL_STATES:
            return
        async_update_multiple_entries_issue(hass)

    return async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _async_entry_changed)


@callback
def async_update_multiple_entries_issue(hass: HomeAssistant) -> None:
    """Создать или снять замечание о лишних записях SberHome.

    Считаются только записи, которые Home Assistant пытается загрузить:
    игнорированные и отключённые пользователем не мешают. Активной считается
    та запись, которую возьмёт панель, когда текущие переходы завершатся:
    первая в порядке реестра среди загруженных или загружающихся (правило
    ``get_config_entry``). Если такой нет — первая запись в реестре.

    Предупреждение в журнал пишется только когда замечание появляется или
    меняется его текст, а не при каждом изменении записи.

    Args:
        hass: Home Assistant.
    """
    entries = hass.config_entries.async_entries(
        DOMAIN, include_ignore=False, include_disabled=False
    )
    if len(entries) < 2:
        ir.async_delete_issue(hass, DOMAIN, ISSUE_ID)
        return

    active = next(
        (entry for entry in entries if entry.state in _EXPECTED_LOADED_STATES),
        entries[0],
    )
    others = [entry for entry in entries if entry.entry_id != active.entry_id]
    placeholders = {
        "count": str(len(entries)),
        "active": active.title,
        "others": ", ".join(f"«{entry.title}»" for entry in others),
    }

    existing = ir.async_get(hass).async_get_issue(DOMAIN, ISSUE_ID)
    if existing is None or existing.translation_placeholders != placeholders:
        LOGGER.warning(
            "SberHome поддерживает один аккаунт Сбера, а записей интеграции %s. "
            "Панель SberHome работает только с записью «%s» (entry_id=%s); "
            "остальные (%s) из панели не управляются. Удалите лишние записи в "
            "«Настройки → Устройства и службы → SberHome».",
            len(entries),
            active.title,
            active.entry_id,
            ", ".join(f"«{entry.title}» (entry_id={entry.entry_id})" for entry in others),
        )

    ir.async_create_issue(
        hass,
        DOMAIN,
        ISSUE_ID,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key=ISSUE_ID,
        translation_placeholders=placeholders,
    )
